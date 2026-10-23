"""Family B: deduplicate, filter, and aggregate an order table into a CSV summary.

Primary path: aggregate_table. Alternative path: read_file + write_file by hand.
"""

from __future__ import annotations

import csv
import io
import json
from decimal import Decimal, InvalidOperation

from ..constants import GRADER_DIR, INPUT_DIR, OUTPUT_DIR
from ..core import Task, ToolError, ToolSpec
from ..util import arg, norm_path, safe_norm

FAMILY = "clean_table"
PRIMARY_TOOL = "aggregate_table"
CUSTOMERS = ["Acme Corp", "Birch LLC", "Cobalt Inc", "Delta Foods", "Evergreen Co",
             "Fjord Ltd", "Granite AG", "Harbor Supply"]
HEADER = ["order_id", "customer", "amount", "status"]


def _solve(rows: list[dict]) -> list[list[str]]:
    seen, totals = set(), {}
    for r in rows:
        if r["order_id"] in seen:
            continue
        seen.add(r["order_id"])
        if r["status"] == "cancelled":
            continue
        totals[r["customer"]] = totals.get(r["customer"], Decimal("0")) + Decimal(r["amount"])
    return [[c, f"{totals[c]:.2f}"] for c in sorted(totals)]


def _to_csv(header: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def generate(rng, idx: int) -> Task:
    src = f"{INPUT_DIR}/orders_{idx:03d}.csv"
    dst = f"{OUTPUT_DIR}/summary_{idx:03d}.csv"
    customers = rng.sample(CUSTOMERS, 3)
    n = rng.randint(5, 7)
    ids = rng.sample(range(1000, 10000), n)
    rows = [{"order_id": str(ids[i]), "customer": rng.choice(customers),
             "amount": f"{rng.randint(500, 20000) / 100:.2f}", "status": "completed"} for i in range(n)]
    for i in rng.sample(range(n), rng.randint(1, 2)):
        rows[i]["status"] = "cancelled"
    for _ in range(rng.randint(1, 2)):
        j = rng.randrange(len(rows))
        rows.insert(rng.randint(j + 1, len(rows)), dict(rows[j]))

    expected = _solve(rows)
    out_text = _to_csv(["customer", "total"], expected)
    instruction = (
        f"Clean the order table {src} and write a per-customer summary to {dst}. "
        "Steps: (1) remove duplicate rows that share an order_id, keeping the first occurrence; "
        "(2) drop rows whose status is 'cancelled'; (3) compute the total amount per customer. "
        "The output must be a CSV file with the header customer,total and one row per customer, "
        "sorted alphabetically by customer, with totals written with exactly two decimal places."
    )
    files = {
        src: _to_csv(HEADER, [[r[c] for c in HEADER] for r in rows]),
        f"{GRADER_DIR}/expected_output.csv": out_text,
        f"{GRADER_DIR}/config.json": json.dumps({"output": dst, "check": "exact_match"}),
    }
    primary = [{"tool": PRIMARY_TOOL, "args": {
        "src": src, "dst": dst, "group_by": "customer", "sum_column": "amount",
        "dedupe_on": "order_id", "drop_if": {"status": "cancelled"}}}]
    alt = [{"tool": "read_file", "args": {"path": src}},
           {"tool": "write_file", "args": {"path": dst, "content": out_text}}]
    return Task(task_id=f"{FAMILY}-{idx:03d}", family=FAMILY, instruction=instruction, files=files,
                resource=src, resource_label=f"The file {src}", primary_tool=PRIMARY_TOOL,
                alt_tools=["read_file", "write_file"], output_path=dst, expected=expected,
                primary_plan=primary, alt_plan=alt)


def _aggregate(env, args: dict) -> str:
    src, dst = norm_path(arg(args, "src")), norm_path(arg(args, "dst"))
    group_by, sum_column = arg(args, "group_by"), arg(args, "sum_column")
    dedupe_on = arg(args, "dedupe_on", required=False)
    drop_if = arg(args, "drop_if", dict, required=False, default={}) or {}
    if src not in env.files:
        raise ToolError(f"Error: no such file: {src}")
    reader = csv.DictReader(io.StringIO(env.files[src]))
    header = reader.fieldnames or []
    needed = [group_by, sum_column] + ([dedupe_on] if dedupe_on else []) + [str(c) for c in drop_if]
    missing = [c for c in needed if c not in header]
    if missing:
        raise ToolError(f"Error: unknown column(s): {', '.join(missing)}")
    seen, totals = set(), {}
    for row in reader:
        if dedupe_on:
            if row[dedupe_on] in seen:
                continue
            seen.add(row[dedupe_on])
        if any(row[str(c)] == str(v) for c, v in drop_if.items()):
            continue
        try:
            amount = Decimal(row[sum_column])
        except InvalidOperation:
            raise ToolError(f"Error: non-numeric value in column {sum_column}: {row[sum_column]!r}")
        totals[row[group_by]] = totals.get(row[group_by], Decimal("0")) + amount
    rows = [[k, f"{totals[k]:.2f}"] for k in sorted(totals)]
    env.write(dst, _to_csv([group_by, "total"], rows))
    return f"Wrote {len(rows)} groups to {dst}."


def tools() -> list[ToolSpec]:
    return [ToolSpec(
        name=PRIMARY_TOOL,
        signature=("aggregate_table(src: str, dst: str, group_by: str, sum_column: str, "
                   "dedupe_on: str | null, drop_if: dict[str, str] | null)"),
        description=("Reads a CSV table, optionally removes rows whose dedupe_on value was already seen "
                     "(keeping the first), drops rows matching any column=value pair in drop_if, sums "
                     "sum_column per group_by value, and writes a CSV with header <group_by>,total sorted "
                     "by group, totals to two decimals."),
        fn=_aggregate,
        touches=lambda task, a: safe_norm(a.get("src")) == task.resource,
        path_args_read=("src",), path_args_write=("dst",),
    )]


def check(content: str, expected) -> bool:
    try:
        rows = [r for r in csv.reader(io.StringIO(content.strip())) if r]
    except (csv.Error, AttributeError):
        return False
    if not rows or [h.strip().lower() for h in rows[0]] != ["customer", "total"]:
        return False
    body = rows[1:]
    if len(body) != len(expected):
        return False
    for got, (cust, total) in zip(body, expected):
        if len(got) != 2 or got[0].strip() != cust:
            return False
        try:
            if abs(Decimal(got[1].strip()) - Decimal(total)) > Decimal("0.005"):
                return False
        except InvalidOperation:
            return False
    return True
