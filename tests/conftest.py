import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from persist.tasks import generate_suite  # noqa: E402


@pytest.fixture(scope="session")
def tasks():
    return generate_suite(n_per_family=10, seed=0)


@pytest.fixture(scope="session")
def by_family(tasks):
    out = {}
    for t in tasks:
        out.setdefault(t.family, t)
    return out
