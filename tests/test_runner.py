import json

import pytest

from agent.config import Settings
from agent.llm import FakeLLM, ToolCall, Turn
from agent.runner import Deps, main

PLAN = {"plan": "1. fix cart_total", "risks": [], "files": ["shop/cart.py"]}
IMPL = {"changes": "fixed", "tests": "pytest ok", "open_questions": []}


def finish_turn(summary):
    return Turn(text="", tool_calls=[ToolCall("t", "finish", {"summary": summary})], input_tokens=10,
                output_tokens=5, stop_reason="tool_use", raw_content=[{"text": "x"}])


class FakeGitHub:
    def __init__(self):
        self.comments, self.pushed, self.prs = [], [], []

    def issue(self, n):
        return {"number": n, "title": "Cart bug", "body": "fix it"}

    def clone(self, dest):
        dest.mkdir(parents=True)
        (dest / "app.py").write_text("x = 1\n")

    def comment(self, n, body):
        self.comments.append(body)

    def push_branch(self, root, branch, message):
        self.pushed.append(branch)

    def create_pr(self, branch, title, body):
        self.prs.append((branch, title, body))
        return "https://github.com/o/r/pull/9"


class FakeStore:
    def __init__(self, state, **fields):
        self.item = {"issue": 5, "state": state, **fields}
        self.usage = []

    def get(self, n):
        return dict(self.item)

    def transition(self, n, expected, new, **fields):
        if self.item["state"] != expected:
            return False
        self.item.update(state=new, **fields)
        return True

    def add_usage(self, n, usage):
        self.usage.append(usage)


def deps(tmp_path, store, script, tests_ok=True, settings=None):
    gh = FakeGitHub()
    return gh, Deps(settings=settings or Settings(), github=gh, store=store, llm_for=lambda phase: FakeLLM(script),
                    workdir=tmp_path, run_tests=lambda ws: f"exit code {0 if tests_ok else 1}\n3 passed")


def test_plan_flow_comments_and_waits(tmp_path, capsys):
    store = FakeStore("PLANNING")
    gh, d = deps(tmp_path, store, [finish_turn(PLAN)])
    assert main({"ISSUE_NUMBER": "5", "PHASE": "plan"}, d) == 0
    assert store.item["state"] == "AWAITING_APPROVAL" and json.loads(store.item["plan"]) == PLAN
    assert "/approve" in gh.comments[0] and not gh.pushed
    assert '"Outcome": "AWAITING_APPROVAL"' in capsys.readouterr().out


def test_implement_flow_opens_pr(tmp_path):
    store = FakeStore("IMPLEMENTING", plan=json.dumps(PLAN))
    gh, d = deps(tmp_path, store, [finish_turn(IMPL)])
    assert main({"ISSUE_NUMBER": "5", "PHASE": "implement"}, d) == 0
    assert gh.pushed == ["agent/issue-5"] and gh.prs[0][2].startswith("Closes #5")
    assert store.item["state"] == "PR_OPENED" and store.item["pr_url"].endswith("/pull/9")


def test_implement_refuses_pr_when_tests_fail(tmp_path):
    store = FakeStore("IMPLEMENTING", plan=json.dumps(PLAN))
    gh, d = deps(tmp_path, store, [finish_turn(IMPL)], tests_ok=False)
    assert main({"ISSUE_NUMBER": "5", "PHASE": "implement"}, d) == 1
    assert not gh.pushed and not gh.prs and store.item["state"] == "FAILED"
    assert "tests" in gh.comments[0].lower()


def test_budget_exceeded_comments_and_pushes_nothing(tmp_path):
    store = FakeStore("IMPLEMENTING", plan=json.dumps(PLAN))
    loop_turn = Turn(text="", tool_calls=[ToolCall("t", "list_files", {})], input_tokens=1, output_tokens=1,
                     stop_reason="tool_use", raw_content=[{"text": "x"}])
    gh, d = deps(tmp_path, store, [loop_turn] * 5, settings=Settings(max_iterations=2))
    assert main({"ISSUE_NUMBER": "5", "PHASE": "implement"}, d) == 1
    assert store.item["state"] == "BUDGET_EXCEEDED" and not gh.pushed
    assert "iterations" in gh.comments[0]


def test_unexpected_error_marks_failed_and_redacts(tmp_path):
    store = FakeStore("PLANNING")
    gh, d = deps(tmp_path, store, [])

    def boom(phase):
        raise RuntimeError("bad arn:aws:iam::123456789012:role/x")
    d.llm_for = boom
    assert main({"ISSUE_NUMBER": "5", "PHASE": "plan"}, d) == 1
    assert store.item["state"] == "FAILED"
    assert "123456789012" not in gh.comments[0] and "<account-id>" in gh.comments[0]


def test_wrong_state_does_nothing(tmp_path):
    store = FakeStore("DONE")
    gh, d = deps(tmp_path, store, [finish_turn(PLAN)])
    assert main({"ISSUE_NUMBER": "5", "PHASE": "plan"}, d) == 0
    assert not gh.comments and store.item["state"] == "DONE"


@pytest.mark.parametrize("env", [{}, {"ISSUE_NUMBER": "5", "PHASE": "deploy"}])
def test_bad_env_rejected(tmp_path, env):
    store = FakeStore("PLANNING")
    _, d = deps(tmp_path, store, [])
    assert main(env, d) == 2
