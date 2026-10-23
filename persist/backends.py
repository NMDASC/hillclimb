"""Model backends. Each returns, for every conversation, a list of n sampled completions.

- openai : any OpenAI-compatible /v1/chat/completions server (vLLM serve, SGLang, Ollama,
           LM Studio, mlx_lm.server, or a hosted API). Standard library only.
- vllm   : offline batched generation with vllm.LLM (fastest on a GPU node).
- mock   : random canned actions, for testing the pipeline without a model.
"""

from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


class Backend:
    def sample(self, conversations: list[list[dict]], n: int = 1) -> list[list[str]]:
        raise NotImplementedError


def _apply_soft_no_think(conv: list[dict]) -> list[dict]:
    """Qwen3 soft switch: '/no_think' in the system or user turn disables thinking."""
    conv = [dict(m) for m in conv]
    conv[0]["content"] = conv[0]["content"] + "\n/no_think"
    return conv


class OpenAICompatBackend(Backend):
    def __init__(self, model: str, base_url: str = "http://localhost:8000/v1", api_key: str | None = None,
                 temperature: float = 0.7, top_p: float = 0.8, max_tokens: int = 1024,
                 no_think: str = "template", use_n: bool = True, concurrency: int = 16,
                 timeout: float = 300.0, retries: int = 4, extra_body: dict | None = None):
        self.model, self.base_url = model, base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "EMPTY")
        self.temperature, self.top_p, self.max_tokens = temperature, top_p, max_tokens
        self.no_think, self.use_n, self.concurrency = no_think, use_n, concurrency
        self.timeout, self.retries = timeout, retries
        self.extra_body = extra_body or {}

    def _payload(self, conv: list[dict], n: int) -> dict:
        if self.no_think == "soft":
            conv = _apply_soft_no_think(conv)
        body = {"model": self.model, "messages": conv, "temperature": self.temperature,
                "top_p": self.top_p, "max_tokens": self.max_tokens, "n": n, **self.extra_body}
        if self.no_think == "template":  # honoured by vLLM / SGLang for Qwen3 chat templates
            body["chat_template_kwargs"] = {"enable_thinking": False}
        return body

    def _post(self, body: dict) -> list[str]:
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"})
        delay = 2.0
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read())
                return [c["message"].get("content") or "" for c in data["choices"]]
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt == self.retries:
                    raise RuntimeError(f"request to {self.base_url} failed: {e}") from e
                time.sleep(delay)
                delay *= 2
        return []

    def _sample_one(self, conv: list[dict], n: int) -> list[str]:
        outs: list[str] = []
        if self.use_n:
            outs = self._post(self._payload(conv, n))[:n]
        while len(outs) < n:  # servers that ignore `n` (e.g. Ollama) return one choice
            outs += self._post(self._payload(conv, 1))[:1]
        return outs

    def sample(self, conversations, n=1):
        with ThreadPoolExecutor(self.concurrency) as pool:
            return list(pool.map(lambda c: self._sample_one(c, n), conversations))


class VLLMBackend(Backend):
    def __init__(self, model: str, temperature: float = 0.7, top_p: float = 0.8, top_k: int = 20,
                 max_tokens: int = 1024, no_think: str = "template", seed: int = 0,
                 max_model_len: int = 8192, gpu_memory_utilization: float = 0.9,
                 lora_path: str | None = None, **llm_kwargs):
        from vllm import LLM, SamplingParams  # imported lazily: only needed on GPU nodes
        self._SamplingParams = SamplingParams
        self.llm = LLM(model=model, seed=seed, max_model_len=max_model_len,
                       gpu_memory_utilization=gpu_memory_utilization,
                       enable_lora=lora_path is not None, **llm_kwargs)
        self.lora = None
        if lora_path:
            from vllm.lora.request import LoRARequest
            self.lora = LoRARequest("adapter", 1, lora_path)
        self.temperature, self.top_p, self.top_k = temperature, top_p, top_k
        self.max_tokens, self.no_think, self.seed = max_tokens, no_think, seed

    def sample(self, conversations, n=1):
        if self.no_think == "soft":
            conversations = [_apply_soft_no_think(c) for c in conversations]
        params = self._SamplingParams(n=n, temperature=self.temperature, top_p=self.top_p,
                                      top_k=self.top_k, max_tokens=self.max_tokens, seed=self.seed)
        kwargs = {}
        if self.no_think == "template":
            kwargs["chat_template_kwargs"] = {"enable_thinking": False}
        outs = self.llm.chat(conversations, params, use_tqdm=True, lora_request=self.lora, **kwargs)
        return [[o.text for o in out.outputs] for out in outs]


class MockBackend(Backend):
    """Random mixture of retry / stop / explore / done / garbage, for pipeline tests."""

    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)

    def _one(self, conv):
        last = next((m["content"] for m in reversed(conv) if m["role"] == "assistant"), None)
        options = [
            '{"tool": "stop", "args": {"reason": "mock stop"}}',
            '{"tool": "list_files", "args": {"path": "/data"}}',
            '{"tool": "report_done", "args": {"summary": "mock"}}',
            "I am not sure what to do.",
        ]
        if last:
            options.append(last)
        return self.rng.choice(options)

    def sample(self, conversations, n=1):
        return [[self._one(c) for _ in range(n)] for c in conversations]


def make_backend(name: str, **kw) -> Backend:
    if name == "openai":
        return OpenAICompatBackend(**kw)
    if name == "vllm":
        return VLLMBackend(**kw)
    if name == "mock":
        return MockBackend(seed=kw.get("seed", 0))
    raise ValueError(f"unknown backend {name!r}")
