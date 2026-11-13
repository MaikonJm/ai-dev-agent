import json

from agent.metrics import emit
from agent.report import render_plan_comment, render_pr_body

USAGE = {"input_tokens": 1200, "output_tokens": 300, "cost_usd": 0.0123, "seconds": 42.0, "iterations": 7}


def test_emit_format(capsys):
    emit("CostUSD", 0.5, "None", {"Outcome": "PR_OPENED"})
    doc = json.loads(capsys.readouterr().out)
    assert doc["CostUSD"] == 0.5 and doc["Outcome"] == "PR_OPENED"
    metric = doc["_aws"]["CloudWatchMetrics"][0]
    assert metric["Namespace"] == "AIDevAgent" and metric["Dimensions"] == [["Outcome"]]
    assert metric["Metrics"] == [{"Name": "CostUSD", "Unit": "None"}]


def test_render_plan_has_commands():
    body = render_plan_comment(5, {"plan": "1. fix", "risks": ["none"], "files": ["a.py"]}, USAGE)
    assert "1. fix" in body and "`a.py`" in body
    assert "/approve" in body and "/revise" in body
    assert "1200 in / 300 out" in body and "US$ 0.0123" in body


def test_render_pr_closes_issue():
    body = render_pr_body(5, {"changes": "fixed", "tests": "ok", "open_questions": ["q?"]}, USAGE, "3 passed")
    assert body.startswith("Closes #5") and "fixed" in body and "q?" in body and "3 passed" in body
    assert "human review" in body.lower()
