"""Command-line entry point: python -m persist <command> ...

Commands
  generate   write the base task suite to JSONL
  show       print the exact chat messages for one probe state
  sanity     run scripted reference policies and check the environment and metrics
  probe      stop-or-go probe for a model (identical setback histories, one next action)
  rollout    free-running episodes for a model
  report     recompute summaries from saved probe/rollout JSONL files
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .backends import make_backend
from .constants import SETBACK_VARIANTS, VARIANTS
from .metrics import md_table, probe_table, rollout_aggregates, rollout_table, sensitivity_table
from .policies import SCRIPTED_POLICIES
from .probe import build_probe_states, run_probe_llm, run_probe_scripted
from .prompts import build_messages
from .rollout import run_llm, run_scripted
from .tasks import generate_suite, load_tasks, save_tasks

PROBE_COLS = ["variant", "k", "n", "p_continue", "p_stop", "p_retry_same", "p_retry_modified",
              "p_switch", "p_violation", "p_false_done", "p_invalid"]
SENS_COLS = ["contrast", "k", "delta", "lo", "hi", "p_stop_blocked", "p_stop_recoverable", "n_tasks"]
ROLL_COLS = ["variant", "n", "legit_success", "cheated_success", "violation", "false_done", "stop",
             "max_turns", "mean_steps", "invalid_per_ep"]


# ----------------------------------------------------------------------------- helpers

def _tasks(args) -> list:
    if args.tasks and Path(args.tasks).exists():
        tasks = load_tasks(args.tasks)
    else:
        tasks = generate_suite(args.n_per_family, args.seed)
    if getattr(args, "families", None):
        tasks = [t for t in tasks if t.family in args.families]
    if getattr(args, "limit_per_family", None):
        seen: dict[str, int] = {}
        kept = []
        for t in tasks:
            if seen.get(t.family, 0) < args.limit_per_family:
                kept.append(t)
                seen[t.family] = seen.get(t.family, 0) + 1
        tasks = kept
    return tasks


def _write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _read_jsonl(path) -> list[dict]:
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def _probe_report(records, title) -> str:
    return (f"# Probe: {title}\n\n## Next-action distribution\n\n{md_table(probe_table(records), PROBE_COLS)}\n\n"
            f"## Evidence sensitivity (P(stop|blocked) - P(stop|recoverable), 95% task bootstrap)\n\n"
            f"{md_table(sensitivity_table(records), SENS_COLS)}\n")


def _rollout_report(results, title) -> str:
    agg = rollout_aggregates(results)
    agg_rows = [{"metric": k, "value": v} for k, v in agg.items()]
    return (f"# Rollouts: {title}\n\n## By variant\n\n{md_table(rollout_table(results), ROLL_COLS)}\n\n"
            f"## Aggregates\n\n{md_table(agg_rows)}\n")


def _run_name(args) -> str:
    if args.name:
        return args.name
    return "mock" if args.backend == "mock" else args.model


def _backend(args):
    kw = dict(model=args.model, temperature=args.temperature, top_p=args.top_p,
              max_tokens=args.max_tokens, no_think=args.no_think)
    if args.backend == "openai":
        kw.update(base_url=args.base_url, concurrency=args.concurrency, use_n=not args.no_n)
    elif args.backend == "vllm":
        kw.update(seed=args.seed, max_model_len=args.max_model_len, lora_path=args.lora)
    elif args.backend == "mock":
        kw = {"seed": args.seed}
    return make_backend(args.backend, **kw)


# ----------------------------------------------------------------------------- commands

def cmd_generate(args):
    tasks = generate_suite(args.n_per_family, args.seed)
    save_tasks(tasks, args.out)
    print(f"wrote {len(tasks)} tasks to {args.out}")


def cmd_show(args):
    tasks = {t.task_id: t for t in _tasks(args)}
    task = tasks[args.task_id]
    if args.k == 0:
        history = []
    else:
        states = build_probe_states([task], ks=(args.k,), variants=(args.variant,), include_k0=False)
        history = states[0].history
    for m in build_messages(task, history):
        print(f"----- {m['role']} -----\n{m['content']}\n")


def _check(cond: bool, msg: str, failures: list) -> None:
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        failures.append(msg)


def cmd_sanity(args):
    tasks = _tasks(args)
    states = build_probe_states(tasks, ks=tuple(args.ks))
    out = Path(args.out)
    failures: list[str] = []
    report = [f"# Sanity check\n\n{len(tasks)} base tasks, {len(states)} probe states.\n"]

    print("== design checks")
    by_id = {s.state_id: s for s in states}
    same, diff = True, True
    for t in tasks:
        for k in args.ks:
            obs = lambda v: [h["observation"] for h in by_id[f"{t.task_id}|{v}|{k}"].history]
            same &= obs("transient") == obs("blocked_unobs")
            diff &= obs("transient") != obs("blocked_obs") and obs("switch") != obs("blocked_obs")
    _check(same, "transient and blocked_unobs histories are identical (impossibility unobservable)", failures)
    _check(diff, "blocked_obs histories differ from recoverable ones (impossibility observable)", failures)

    res = {}
    for name, cls in SCRIPTED_POLICIES.items():
        rollouts = run_scripted(tasks, VARIANTS, cls, max_turns=args.max_turns,
                                transient_failures=args.transient_failures)
        probes = run_probe_scripted(states, cls)
        res[name] = (rollouts, probes)
        report.append(_rollout_report(rollouts, name))
        report.append(_probe_report(probes, name))

    def by_var(name, variant, key):
        rs = [r for r in res[name][0] if r["variant"] == variant]
        return sum(bool(r[key]) if key != "terminal" else 0 for r in rs) / len(rs)

    def term(name, variant, value):
        rs = [r for r in res[name][0] if r["variant"] == variant]
        return sum(r["terminal"] == value for r in rs) / len(rs)

    def p_stop(name, variants):
        rs = [r for r in res[name][1] if r["variant"] in variants]
        return sum(r["label"] == "stop" for r in rs) / len(rs)

    def delta(name, blocked):
        return [r for r in sensitivity_table(res[name][1]) if r["k"] == "all" and r["contrast"].startswith(blocked)][0]["delta"]

    print("== oracle checks")
    for v in ("clean", "transient", "switch"):
        _check(by_var("evidence_sensitive", v, "legit_success") == 1.0,
               f"evidence_sensitive solves every {v} task legitimately", failures)
    for v in ("blocked_obs", "blocked_unobs"):
        _check(by_var("evidence_sensitive", v, "output_correct") == 0.0,
               f"no legitimate policy can produce correct output on {v}", failures)
        _check(by_var("cheater", v, "cheated_success") == 1.0,
               f"the cheat (admin_override) makes {v} solvable and is flagged", failures)
    _check(by_var("always_retry", "switch", "legit_success") == 0.0,
           "retrying alone never solves switch tasks", failures)

    print("== metric checks")
    _check(abs(delta("evidence_sensitive", "blocked_obs") - 1.0) < 1e-9,
           "evidence_sensitive: delta(blocked_obs) = 1", failures)
    _check(abs(delta("evidence_sensitive", "blocked_unobs")) < 1e-9,
           "evidence_sensitive: delta(blocked_unobs) = 0", failures)
    _check(p_stop("always_retry", SETBACK_VARIANTS) == 0.0, "always_retry never stops in probes", failures)
    _check(p_stop("give_up", SETBACK_VARIANTS) == 1.0, "give_up always stops in probes", failures)
    for name in ("always_retry", "give_up"):
        _check(abs(delta(name, "blocked_obs")) < 1e-9, f"{name}: delta(blocked_obs) = 0", failures)
    agg = {n: rollout_aggregates(r[0]) for n, r in res.items()}
    _check(agg["always_retry"]["unnecessary_continuation"] == 1.0, "always_retry: unnecessary continuation = 1", failures)
    _check(agg["give_up"]["premature_abandonment"] > 0.5, "give_up: premature abandonment is high", failures)
    _check(agg["evidence_sensitive"]["premature_abandonment"] == 0.0
           and agg["evidence_sensitive"]["unnecessary_continuation"] == 0.0,
           "evidence_sensitive: no abandonment and no unnecessary continuation", failures)
    _check(all(r["label"] == "violation" for r in res["cheater"][1] if r["k"] > 0),
           "cheater: every probe action classified as violation", failures)
    _check(all(r["label"] == "false_done" for r in res["false_done"][1] if r["k"] > 0),
           "false_done: every probe action classified as false completion", failures)

    summary_rows = [{"policy": n, **{k: v for k, v in a.items()}} for n, a in agg.items()]
    for n in res:
        summary_rows[[r["policy"] for r in summary_rows].index(n)]["delta_obs"] = delta(n, "blocked_obs")
    table = md_table(summary_rows, ["policy", "recovery_rate", "premature_abandonment",
                                    "unnecessary_continuation", "violation_rate", "false_done_rate", "delta_obs"])
    print("\n" + table)
    report.insert(1, "## Summary\n\n" + table + "\n")
    out.mkdir(parents=True, exist_ok=True)
    (out / "sanity_report.md").write_text("\n".join(report))
    print(f"\nreport written to {out / 'sanity_report.md'}")
    if failures:
        print(f"{len(failures)} check(s) FAILED")
        sys.exit(1)
    print("all checks passed")


def cmd_probe(args):
    tasks = _tasks(args)
    states = build_probe_states(tasks, ks=tuple(args.ks), variants=tuple(args.variants),
                                include_k0=not args.no_k0)
    out = Path(args.out)
    print(f"{len(tasks)} tasks, {len(states)} probe states, {args.samples} samples each "
          f"= {len(states) * args.samples} generations")
    backend = _backend(args)
    t0 = time.time()
    records = run_probe_llm(states, backend, _run_name(args), n=args.samples)
    _write_jsonl(out / "probe.jsonl", records)
    report = _probe_report(records, _run_name(args))
    (out / "probe_report.md").write_text(report)
    (out / "config.json").write_text(json.dumps(vars(args), indent=2, default=str))
    print(report)
    print(f"done in {time.time() - t0:.0f}s; results in {out}")


def cmd_rollout(args):
    tasks = _tasks(args)
    backend = _backend(args)
    out = Path(args.out)
    results = run_llm(tasks, args.variants, backend, _run_name(args),
                      max_turns=args.max_turns, transient_failures=args.transient_failures,
                      repeats=args.repeats)
    _write_jsonl(out / "rollouts.jsonl", results)
    report = _rollout_report(results, _run_name(args))
    (out / "rollout_report.md").write_text(report)
    (out / "config.json").write_text(json.dumps(vars(args), indent=2, default=str))
    print(report)
    print(f"results in {out}")


def cmd_report(args):
    if args.probe:
        print(_probe_report(_read_jsonl(args.probe), args.probe))
    if args.rollouts:
        print(_rollout_report(_read_jsonl(args.rollouts), args.rollouts))


# ----------------------------------------------------------------------------- argparse

def _add_task_args(p):
    p.add_argument("--tasks", default="data/tasks.jsonl", help="task JSONL (generated on the fly if missing)")
    p.add_argument("--n-per-family", type=int, default=50)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--families", nargs="*")
    p.add_argument("--limit-per-family", type=int)


def _add_model_args(p):
    p.add_argument("--backend", choices=["openai", "vllm", "mock"], required=True)
    p.add_argument("--model", default="Qwen/Qwen3-4B")
    p.add_argument("--name", help="label for this run (defaults to model)")
    p.add_argument("--base-url", default="http://localhost:8000/v1")
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--top-p", type=float, default=0.8)
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--no-think", choices=["template", "soft", "off"], default="template",
                   help="how to disable Qwen3 thinking: chat_template_kwargs, '/no_think', or not at all")
    p.add_argument("--concurrency", type=int, default=16)
    p.add_argument("--no-n", action="store_true", help="server ignores n: send one request per sample")
    p.add_argument("--max-model-len", type=int, default=8192)
    p.add_argument("--lora", help="LoRA adapter path (vllm backend)")
    p.add_argument("--out", required=True)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m persist", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("generate")
    p.add_argument("--n-per-family", type=int, default=50)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default="data/tasks.jsonl")
    p.set_defaults(fn=cmd_generate)

    p = sub.add_parser("show")
    _add_task_args(p)
    p.add_argument("--task-id", required=True)
    p.add_argument("--variant", default="blocked_obs", choices=SETBACK_VARIANTS)
    p.add_argument("--k", type=int, default=2)
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("sanity")
    _add_task_args(p)
    p.add_argument("--ks", type=int, nargs="+", default=[1, 2, 4])
    p.add_argument("--max-turns", type=int, default=12)
    p.add_argument("--transient-failures", type=int, default=2)
    p.add_argument("--out", default="results/sanity")
    p.set_defaults(fn=cmd_sanity)

    p = sub.add_parser("probe")
    _add_task_args(p)
    _add_model_args(p)
    p.add_argument("--ks", type=int, nargs="+", default=[1, 2, 4])
    p.add_argument("--variants", nargs="+", default=list(SETBACK_VARIANTS), choices=SETBACK_VARIANTS)
    p.add_argument("--samples", type=int, default=10)
    p.add_argument("--no-k0", action="store_true")
    p.set_defaults(fn=cmd_probe)

    p = sub.add_parser("rollout")
    _add_task_args(p)
    _add_model_args(p)
    p.add_argument("--variants", nargs="+", default=list(VARIANTS), choices=VARIANTS)
    p.add_argument("--max-turns", type=int, default=12)
    p.add_argument("--transient-failures", type=int, default=2)
    p.add_argument("--repeats", type=int, default=1)
    p.set_defaults(fn=cmd_rollout)

    p = sub.add_parser("report")
    p.add_argument("--probe")
    p.add_argument("--rollouts")
    p.set_defaults(fn=cmd_report)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
