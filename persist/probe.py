"""Stop-or-go probes: identical standardized setback histories, then one next action."""

from __future__ import annotations

from dataclasses import dataclass, field

from .actions import parse_action
from .classify import classify_next
from .constants import DEFAULT_OVERRIDE_DESC, SETBACK_VARIANTS
from .core import Task
from .env import ToolEnv, tool_map
from .prompts import build_messages


@dataclass
class ProbeState:
    state_id: str
    task: Task
    variant: str            # a setback variant, or "k0" for the no-history baseline
    k: int                  # number of failed primary-tool attempts in the history
    history: list[dict] = field(default_factory=list)

    @property
    def last_action(self) -> dict | None:
        return self.history[-1]["action"] if self.history else None


def build_probe_states(tasks: list[Task], ks=(1, 2, 4), variants=SETBACK_VARIANTS,
                       include_k0=True) -> list[ProbeState]:
    """Every history repeats the task's primary call k times; only the observations differ."""
    states = []
    for t in tasks:
        if include_k0:
            states.append(ProbeState(f"{t.task_id}|k0|0", t, "k0", 0, []))
        for v in variants:
            for k in ks:
                env = ToolEnv(t, v, transient_failures=k, max_turns=k + 10)
                hist = []
                for _ in range(k):
                    obs = env.step(t.primary_call)
                    if not obs.startswith("Error"):
                        raise AssertionError(f"setback did not fail: {t.task_id} {v} k={k}: {obs}")
                    hist.append({"action": t.primary_call, "raw": None, "observation": obs})
                states.append(ProbeState(f"{t.task_id}|{v}|{k}", t, v, k, hist))
    return states


def _record(state: ProbeState, sample: int, policy: str, action, raw=None) -> dict:
    label = classify_next(action, state.last_action, tool_map(state.task))
    return {"state_id": state.state_id, "task_id": state.task.task_id, "family": state.task.family,
            "variant": state.variant, "k": state.k, "sample": sample, "policy": policy,
            "label": label, "action": action, "raw": raw}


def run_probe_scripted(states: list[ProbeState], policy_cls) -> list[dict]:
    records = []
    for s in states:
        pol = policy_cls()
        pol.reset(s.task)
        for h in s.history:
            pol.observe(h["action"], h["observation"])
        records.append(_record(s, 0, pol.name, pol.act()))
    return records


def run_probe_llm(states: list[ProbeState], backend, policy_name: str, n: int = 10,
                  override_desc: str = DEFAULT_OVERRIDE_DESC) -> list[dict]:
    convs = [build_messages(s.task, s.history, override_desc) for s in states]
    outs = backend.sample(convs, n=n)
    records = []
    for s, samples in zip(states, outs):
        for j, raw in enumerate(samples):
            records.append(_record(s, j, policy_name, parse_action(raw), raw))
    return records
