"""Entry point of the Fargate task: one phase of one issue, then exit."""

import json
import os
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from agent import loop
from agent.budget import Budget
from agent.config import Settings
from agent.metrics import emit
from agent.redact import redact
from agent.report import render_plan_comment, render_pr_body
from agent.tools import Workspace

PHASE_STATE = {"plan": "PLANNING", "implement": "IMPLEMENTING"}


@dataclass
class Deps:
    settings: Settings
    github: object
    store: object
    llm_for: Callable[[str], object]
    workdir: Path = field(default_factory=lambda: Path(tempfile.mkdtemp(prefix="agent-")))
    run_tests: Callable[[Workspace], str] = lambda ws: ws.run_command("pytest -q")


def build_deps(settings: Settings) -> Deps:  # pragma: no cover - wiring for AWS
    import boto3

    from agent.github_app import GitHubApp
    from agent.llm import BedrockLLM
    from agent.store import TaskStore

    ssm = boto3.client("ssm", region_name=settings.region)
    key = ssm.get_parameter(Name=settings.github_key_param, WithDecryption=True)["Parameter"]["Value"]
    github = GitHubApp(settings.github_app_id, key, settings.github_installation_id, settings.github_repo)
    models = {"plan": settings.plan_model_id, "implement": settings.impl_model_id}
    return Deps(settings=settings, github=github, store=TaskStore(settings.table_name, region=settings.region),
                llm_for=lambda phase: BedrockLLM(models[phase], region=settings.region))


def _metrics(outcome: str, usage: dict) -> None:
    dims = {"Outcome": outcome}
    emit("TasksCompleted", 1, "Count", dims)
    emit("TokensIn", usage.get("input_tokens", 0), "Count", dims)
    emit("TokensOut", usage.get("output_tokens", 0), "Count", dims)
    emit("CostUSD", usage.get("cost_usd", 0), "None", dims)
    emit("DurationSeconds", usage.get("seconds", 0), "Seconds", dims)


def main(env: Mapping[str, str] = os.environ, deps: Deps | None = None) -> int:
    phase = env.get("PHASE")
    if phase not in PHASE_STATE or not env.get("ISSUE_NUMBER", "").isdigit():
        print(json.dumps({"level": "ERROR", "msg": "ISSUE_NUMBER and PHASE=plan|implement are required"}))
        return 2
    issue = int(env["ISSUE_NUMBER"])
    feedback = env.get("FEEDBACK") or None
    deps = deps or build_deps(Settings.from_env(env))
    s, gh, store = deps.settings, deps.github, deps.store
    expected = PHASE_STATE[phase]

    item = store.get(issue)
    if not item or item.get("state") != expected:
        print(json.dumps({"level": "INFO", "msg": f"issue {issue} not in {expected}, nothing to do"}))
        return 0

    budget = Budget(s.max_iterations, s.max_tokens, s.max_seconds, s.max_cost_usd)
    try:
        data = gh.issue(issue)
        task = f"#{issue} {data.get('title', '')}\n\n{data.get('body') or ''}"
        root = deps.workdir / "repo"
        gh.clone(root)
        ws = Workspace(root)
        plan = loop.summary_text(json.loads(item["plan"])) if item.get("plan") else None
        result = loop.run_phase(phase, task, ws, deps.llm_for(phase), budget, feedback=feedback, plan=plan)
        store.add_usage(issue, result.usage)

        if result.status == "budget_exceeded":
            gh.comment(issue, f"⚠️ Stopped: the {result.summary['limit']} budget for this task ran out. "
                              "Nothing was pushed. Reply `/revise <feedback>` to try again with a narrower scope.")
            store.transition(issue, expected, "BUDGET_EXCEEDED")
            _metrics("BUDGET_EXCEEDED", result.usage)
            return 1
        if result.status == "error":
            raise RuntimeError(result.summary.get("error", "agent error"))

        if phase == "plan":
            gh.comment(issue, render_plan_comment(issue, result.summary, result.usage))
            store.transition(issue, expected, "AWAITING_APPROVAL", plan=json.dumps(result.summary))
            _metrics("AWAITING_APPROVAL", result.usage)
            return 0

        test_output = deps.run_tests(ws)
        if not test_output.startswith("exit code 0"):
            gh.comment(issue, "❌ I could not make the tests pass, so I did not open a PR.\n\n```\n"
                              f"{test_output[-2000:]}\n```\nReply `/revise <feedback>` to try again.")
            store.transition(issue, expected, "FAILED")
            _metrics("FAILED", result.usage)
            return 1
        branch = f"agent/issue-{issue}"
        gh.push_branch(root, branch, f"Fix #{issue}: {data.get('title', '')}")
        url = gh.create_pr(branch, f"🤖 {data.get('title', '')}", render_pr_body(issue, result.summary,
                                                                                result.usage, test_output))
        store.transition(issue, expected, "PR_OPENED", pr_url=url)
        gh.comment(issue, f"✅ Pull request opened: {url}")
        _metrics("PR_OPENED", result.usage)
        return 0
    except Exception as exc:  # noqa: BLE001 - every failure must be reported on the issue
        message = redact(f"{type(exc).__name__}: {exc}")[:500]
        print(json.dumps({"level": "ERROR", "issue": issue, "msg": message}))
        try:
            gh.comment(issue, f"❌ The agent failed: `{message}`. Reply `/revise <feedback>` to try again.")
        finally:
            store.transition(issue, expected, "FAILED")
            _metrics("FAILED", budget.snapshot())
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
