from pathlib import Path

import pytest

from evals.run_evals import load_cases, summarize


def test_load_cases_has_required_fields():
    cases = load_cases(Path("evals/cases.yaml"))
    assert len(cases) == 5
    for case in cases:
        assert {"id", "title", "body", "acceptance_test"} <= set(case)
        assert case["acceptance_test"]["path"].startswith("tests/")


def test_summarize():
    results = [
        {"id": "a", "passed": True, "cost_usd": 0.2, "seconds": 100, "tokens": 1000},
        {"id": "b", "passed": False, "cost_usd": 0.4, "seconds": 300, "tokens": 3000},
    ]
    s = summarize(results)
    assert s["cases"] == 2 and s["passed"] == 1 and s["success_rate"] == 0.5
    assert s["mean_cost_usd"] == pytest.approx(0.3) and s["max_cost_usd"] == 0.4
    assert s["mean_seconds"] == 200


def test_summarize_empty():
    assert summarize([])["success_rate"] == 0.0
