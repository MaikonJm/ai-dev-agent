"""Markdown for the plan comment and the pull request body."""


def _usage_line(usage: dict) -> str:
    return (f"<sub>{usage.get('input_tokens', 0)} in / {usage.get('output_tokens', 0)} out tokens · "
            f"US$ {usage.get('cost_usd', 0):.4f} · {usage.get('seconds', 0):.0f} s · "
            f"{usage.get('iterations', 0)} steps</sub>")


def _bullets(items: list) -> str:
    return "\n".join(f"- {i}" for i in items) if items else "- none"


def render_plan_comment(issue: int, summary: dict, usage: dict) -> str:
    files = ", ".join(f"`{f}`" for f in summary.get("files", [])) or "none"
    return "\n".join([
        "### 🤖 Proposed plan", "", summary.get("plan", ""), "",
        f"**Files:** {files}", "", "**Risks:**", _bullets(summary.get("risks", [])), "",
        "Reply `/approve` to let me implement it, or `/revise <feedback>` to change the plan.", "",
        _usage_line(usage),
    ])


def render_pr_body(issue: int, summary: dict, usage: dict, test_output: str) -> str:
    return "\n".join([
        f"Closes #{issue}", "",
        "> 🤖 Opened by the AI Dev Agent. It cannot merge: this PR needs human review.", "",
        "## What changed", summary.get("changes", ""), "",
        "## How it was tested", summary.get("tests", ""), "",
        "<details><summary>Last test run</summary>", "", "```", test_output[-3000:], "```", "</details>", "",
        "## Open questions", _bullets(summary.get("open_questions", [])), "",
        _usage_line(usage),
    ])
