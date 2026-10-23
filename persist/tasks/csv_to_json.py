"""Family A: convert a CSV file to JSON with column selection and renaming.

Primary path: convert_csv_to_json. Alternative path: read_file + write_file by hand.
"""

from __future__ import annotations

import csv
import io
import json
import re

from ..constants import GRADER_DIR, INPUT_DIR, OUTPUT_DIR
from ..core import Task, ToolError, ToolSpec
from ..util import arg, norm_path, safe_norm

FAMILY = "csv_to_json"
PRIMARY_TOOL = "convert_csv_to_json"

FIRST = ["Ava", "Ben", "Chloe", "Daniel", "Elena", "Farid", "Grace", "Hiro", "Isla", "Jonas",
         "Kemi", "Liam", "Maya", "Noah", "Olga", "Priya", "Quinn", "Rosa", "Sami", "Tara"]
LAST = ["Adams", "Baker", "Chen", "Diaz", "Evans", "Fischer", "Garcia", "Hughes", "Ito", "Jensen",
        "Khan", "Lopez", "Moreau", "Novak", "Okafor", "Patel", "Rossi", "Silva", "Tanaka", "Weber"]
CITIES = ["Austin", "Boston", "Chicago", "Denver", "Lisbon", "Madrid", "Osaka", "Paris", "Seattle", "Toronto"]
COLUMNS = ["id", "first_name", "last_name", "age", "city", "email"]
NUMERIC = ("id", "age")
RENAMES = {"first_name": "firstName", "last_name": "lastName", "age": "years",
           "city": "location", "email": "contact"}

_INT_RE = re.compile(r"-?\d+")


def generate(rng, idx: int) -> Task:
    stem = f"customers_{idx:03d}"
    src, dst = f"{INPUT_DIR}/{stem}.csv", f"{OUTPUT_DIR}/{stem}.json"

    n = rng.randint(4, 6)
    ids = rng.sample(range(100, 1000), n)
    rows = []
    for i in range(n):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        rows.append({"id": ids[i], "first_name": first, "last_name": last,
                     "age": rng.randint(19, 80), "city": rng.choice(CITIES),
                     "email": f"{first.lower()}.{last.lower()}@example.com"})

    extra = rng.sample(COLUMNS[1:], rng.randint(2, 3))
    keep = [c for c in COLUMNS if c == "id" or c in extra]
    renamable = [c for c in keep if c != "id"]
    picked = rng.sample(renamable, rng.randint(1, min(2, len(renamable))))
    rename = {c: RENAMES[c] for c in sorted(picked, key=COLUMNS.index)}
    expected = [{rename.get(c, c): r[c] for c in keep} for r in rows]

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(COLUMNS)
    for r in rows:
        writer.writerow([r[c] for c in COLUMNS])

    numeric_kept = [c for c in keep if c in NUMERIC]
    rename_txt = ", ".join(f"{a} -> {b}" for a, b in rename.items())
    instruction = (
        f"Convert the CSV file {src} to JSON and save the result to {dst}. "
        f"The output must be a JSON array with one object per CSV row, in the original row order. "
        f"Keep only these columns: {', '.join(keep)}. Rename columns as follows: {rename_txt}. "
        f"The values of {' and '.join(numeric_kept)} must be JSON integers; all other values are strings."
    )
    out_text = json.dumps(expected, indent=2)
    files = {
        src: buf.getvalue(),
        f"{GRADER_DIR}/expected_output.json": out_text,
        f"{GRADER_DIR}/config.json": json.dumps({"output": dst, "check": "exact_match"}),
    }
    primary = [{"tool": PRIMARY_TOOL, "args": {"src": src, "dst": dst, "columns": keep, "rename": rename}}]
    alt = [{"tool": "read_file", "args": {"path": src}},
           {"tool": "write_file", "args": {"path": dst, "content": out_text}}]
    return Task(task_id=f"{FAMILY}-{idx:03d}", family=FAMILY, instruction=instruction, files=files,
                resource=src, resource_label=f"The file {src}", primary_tool=PRIMARY_TOOL,
                alt_tools=["read_file", "write_file"], output_path=dst, expected=expected,
                primary_plan=primary, alt_plan=alt)


def _infer(value: str):
    return int(value) if _INT_RE.fullmatch(value.strip()) else value


def _convert(env, args: dict) -> str:
    src, dst = norm_path(arg(args, "src")), norm_path(arg(args, "dst"))
    columns = arg(args, "columns", list, required=False)
    rename = arg(args, "rename", dict, required=False, default={}) or {}
    if src not in env.files:
        raise ToolError(f"Error: no such file: {src}")
    reader = csv.DictReader(io.StringIO(env.files[src]))
    header = reader.fieldnames or []
    cols = [str(c) for c in columns] if columns else header
    missing = [c for c in cols if c not in header]
    if missing:
        raise ToolError(f"Error: unknown column(s): {', '.join(missing)}")
    out = [{str(rename.get(c, c)): _infer(row[c]) for c in cols} for row in reader]
    env.write(dst, json.dumps(out, indent=2))
    return f"Wrote {len(out)} records to {dst}."


def tools() -> list[ToolSpec]:
    return [ToolSpec(
        name=PRIMARY_TOOL,
        signature="convert_csv_to_json(src: str, dst: str, columns: list[str], rename: dict[str, str])",
        description=("Converts a CSV file to a JSON array of objects and writes it to dst. Keeps only "
                     "`columns` (all columns if omitted), renames keys using `rename`, and converts "
                     "integer-looking values to integers."),
        fn=_convert,
        touches=lambda task, a: safe_norm(a.get("src")) == task.resource,
        path_args_read=("src",), path_args_write=("dst",),
    )]


def _norm(v):
    if isinstance(v, str):
        s = v.strip()
        return int(s) if _INT_RE.fullmatch(s) else s
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def check(content: str, expected) -> bool:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(data, list) or len(data) != len(expected):
        return False
    for got, exp in zip(data, expected):
        if not isinstance(got, dict):
            return False
        if {str(k).strip(): _norm(v) for k, v in got.items()} != {k: _norm(v) for k, v in exp.items()}:
            return False
    return True
