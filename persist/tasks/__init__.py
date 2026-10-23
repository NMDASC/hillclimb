"""Task families and suite generation."""

from __future__ import annotations

import json
import random
from pathlib import Path

from ..core import Task
from . import api_report, clean_table, csv_to_json

FAMILIES = {m.FAMILY: m for m in (csv_to_json, clean_table, api_report)}


def get_family(name: str):
    return FAMILIES[name]


def generate_suite(n_per_family: int = 50, seed: int = 0, families=None) -> list[Task]:
    """Deterministically generate base tasks. String seeds are hash-seed independent."""
    tasks = []
    for fam in families or FAMILIES:
        for i in range(n_per_family):
            tasks.append(FAMILIES[fam].generate(random.Random(f"{seed}-{fam}-{i}"), i))
    return tasks


def save_tasks(tasks: list[Task], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for t in tasks:
            f.write(t.to_json() + "\n")


def load_tasks(path: str | Path) -> list[Task]:
    with open(path) as f:
        return [Task.from_dict(json.loads(line)) for line in f if line.strip()]
