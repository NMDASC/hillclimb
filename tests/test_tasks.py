import json

from persist.constants import VARIANTS
from persist.env import ToolEnv
from persist.tasks import FAMILIES, generate_suite, get_family, load_tasks, save_tasks


def test_generation_is_deterministic():
    a = [t.to_json() for t in generate_suite(5, seed=3)]
    b = [t.to_json() for t in generate_suite(5, seed=3)]
    c = [t.to_json() for t in generate_suite(5, seed=4)]
    assert a == b and a != c


def test_roundtrip(tmp_path, tasks):
    save_tasks(tasks, tmp_path / "t.jsonl")
    assert [t.to_json() for t in load_tasks(tmp_path / "t.jsonl")] == [t.to_json() for t in tasks]


def test_all_families_present(tasks):
    assert {t.family for t in tasks} == set(FAMILIES)


def test_primary_plan_solves_clean(tasks):
    for t in tasks:
        env = ToolEnv(t, "clean")
        for a in t.primary_plan:
            assert not env.step(a).startswith("Error"), t.task_id
        assert env.evaluate()["legit_success"], t.task_id


def test_alt_plan_solves_switch(tasks):
    for t in tasks:
        env = ToolEnv(t, "switch")
        assert "permanently disabled" in env.step(t.primary_call)
        for a in t.alt_plan:
            assert not env.step(a).startswith("Error"), t.task_id
        assert env.evaluate()["legit_success"], t.task_id


def test_grader_file_matches_expected(tasks):
    for t in tasks:
        grader = [p for p in t.files if p.startswith("/grader/expected_output")][0]
        assert get_family(t.family).check(t.files[grader], t.expected)


def test_checkers_reject_wrong_output(tasks):
    for t in tasks:
        fam = get_family(t.family)
        assert not fam.check("", t.expected)
        assert not fam.check("not json", t.expected)
        assert not fam.check(json.dumps([]), t.expected) or t.expected == []


def test_checkers_are_lenient_on_formatting(by_family):
    t = by_family["csv_to_json"]
    loose = [{k: str(v) for k, v in row.items()} for row in t.expected]  # ints as strings
    assert get_family("csv_to_json").check(json.dumps(loose), t.expected)
    t = by_family["api_report"]
    swapped = {"low_stock": list(reversed(t.expected["low_stock"])), "stock": t.expected["stock"]}
    assert get_family("api_report").check(json.dumps(swapped), t.expected)


def test_every_variant_constructs(tasks):
    for t in tasks[:3]:
        for v in VARIANTS:
            ToolEnv(t, v)
