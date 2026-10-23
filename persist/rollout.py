"""Free-running episodes for scripted policies and LLM backends."""

from __future__ import annotations

from .actions import parse_action
from .core import Task
from .env import ToolEnv
from .prompts import build_messages


def _result(env: ToolEnv, policy: str, repeat: int = 0, keep_log: bool = True) -> dict:
    r = {"task_id": env.task.task_id, "family": env.task.family, "variant": env.variant,
         "policy": policy, "repeat": repeat, **env.evaluate()}
    if keep_log:
        r["log"] = env.log
    return r


def run_scripted(tasks: list[Task], variants, policy_cls, max_turns=12, transient_failures=2,
                 keep_log=False) -> list[dict]:
    results = []
    for task in tasks:
        for variant in variants:
            env = ToolEnv(task, variant, transient_failures=transient_failures, max_turns=max_turns)
            pol = policy_cls()
            pol.reset(task)
            while not env.terminal:
                action = pol.act()
                obs = env.step(action)
                pol.observe(action, obs)
            results.append(_result(env, pol.name, keep_log=keep_log))
    return results


def run_llm(tasks: list[Task], variants, backend, policy_name: str, max_turns=12, transient_failures=2,
            repeats=1, progress=True) -> list[dict]:
    """Steps all episodes in lockstep so each turn is one batched backend call."""
    envs = [ToolEnv(t, v, transient_failures=transient_failures, max_turns=max_turns)
            for t in tasks for v in variants for _ in range(repeats)]
    rep_idx = [i % repeats for i in range(len(envs))]
    histories: list[list[dict]] = [[] for _ in envs]
    turn = 0
    while True:
        active = [i for i, e in enumerate(envs) if not e.terminal]
        if not active:
            break
        turn += 1
        if progress:
            print(f"[rollout] turn {turn}: {len(active)} active episodes", flush=True)
        convs = [build_messages(envs[i].task, histories[i]) for i in active]
        outs = backend.sample(convs, n=1)
        for i, out in zip(active, outs):
            raw = out[0]
            action = parse_action(raw)
            obs = envs[i].step(action, raw=raw)
            histories[i].append({"action": action, "raw": raw, "observation": obs})
    return [_result(e, policy_name, rep_idx[i]) for i, e in enumerate(envs)]
