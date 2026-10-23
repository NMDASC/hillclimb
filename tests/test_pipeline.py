"""End-to-end checks of the probe/rollout pipeline, sanity command, and HTTP backend."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from persist.__main__ import main
from persist.backends import MockBackend, OpenAICompatBackend
from persist.constants import SETBACK_VARIANTS, VARIANTS
from persist.metrics import evidence_sensitivity
from persist.policies import SCRIPTED_POLICIES
from persist.probe import build_probe_states, run_probe_llm, run_probe_scripted
from persist.rollout import run_llm


def test_probe_state_counts(tasks):
    states = build_probe_states(tasks, ks=(1, 2, 4))
    assert len(states) == len(tasks) * (1 + len(SETBACK_VARIANTS) * 3)
    for s in states:
        assert len(s.history) == s.k
        assert all(h["action"] == s.task.primary_call for h in s.history)


def test_scripted_sensitivity(tasks):
    states = build_probe_states(tasks)
    recs = run_probe_scripted(states, SCRIPTED_POLICIES["evidence_sensitive"])
    assert evidence_sensitivity(recs)["delta"] == 1.0
    assert evidence_sensitivity(recs, blocked="blocked_unobs")["delta"] == 0.0


def test_mock_llm_probe_and_rollout(tasks):
    states = build_probe_states(tasks[:6], ks=(1,))
    recs = run_probe_llm(states, MockBackend(seed=1), "mock", n=4)
    assert len(recs) == len(states) * 4
    assert {r["label"] for r in recs} >= {"stop", "invalid"}
    res = run_llm(tasks[:3], VARIANTS, MockBackend(seed=2), "mock", max_turns=5, progress=False)
    assert len(res) == 3 * len(VARIANTS) and all(r["terminal"] for r in res)


class _FakeServer(BaseHTTPRequestHandler):
    bodies: list = []
    honour_n = True

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).bodies.append(body)
        n = body.get("n", 1) if type(self).honour_n else 1
        content = '<think>\n\n</think>\n{"tool": "stop", "args": {"reason": "fake"}}'
        data = json.dumps({"choices": [{"message": {"content": content}} for _ in range(n)]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture
def fake_server():
    _FakeServer.bodies = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _FakeServer)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1"
    srv.shutdown()


def test_openai_backend_payload_and_n(fake_server):
    be = OpenAICompatBackend(model="Qwen/Qwen3-4B", base_url=fake_server, concurrency=2)
    outs = be.sample([[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]], n=3)
    assert len(outs[0]) == 3
    body = _FakeServer.bodies[0]
    assert body["n"] == 3 and body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["temperature"] == 0.7 and body["top_p"] == 0.8


def test_openai_backend_falls_back_when_n_ignored(fake_server):
    _FakeServer.honour_n = False
    try:
        be = OpenAICompatBackend(model="m", base_url=fake_server, no_think="soft")
        outs = be.sample([[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]], n=3)
    finally:
        _FakeServer.honour_n = True
    assert len(outs[0]) == 3 and len(_FakeServer.bodies) == 3
    assert _FakeServer.bodies[0]["messages"][0]["content"].endswith("/no_think")
    assert "chat_template_kwargs" not in _FakeServer.bodies[0]


def test_cli_probe_end_to_end(fake_server, tmp_path):
    out = tmp_path / "probe"
    main(["probe", "--backend", "openai", "--base-url", fake_server, "--tasks", str(tmp_path / "none.jsonl"),
          "--n-per-family", "2", "--samples", "2", "--ks", "1", "2", "--out", str(out)])
    recs = [json.loads(l) for l in (out / "probe.jsonl").read_text().splitlines()]
    assert len(recs) == 6 * (1 + 4 * 2) * 2
    assert all(r["label"] == "stop" for r in recs)
    assert "Evidence sensitivity" in (out / "probe_report.md").read_text()


def test_cli_sanity(tmp_path):
    main(["sanity", "--tasks", str(tmp_path / "none.jsonl"), "--n-per-family", "5", "--out", str(tmp_path)])
    assert (tmp_path / "sanity_report.md").exists()
