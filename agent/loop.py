"""The agent loop: ask the model, run the tools it calls, repeat until `finish` or a limit."""

import json
from dataclasses import dataclass
from typing import Literal

from agent import prompts
from agent.budget import Budget
from agent.tools import READ_ONLY_TOOLS, TOOL_SPECS, Workspace, dispatch

REQUIRED_KEYS = {"plan": {"plan", "risks", "files"}, "implement": {"changes", "tests", "open_questions"}}
MAX_FINISH_FAILURES = 2
MAX_NUDGES = 3


@dataclass
class PhaseResult:
    status: Literal["finished", "budget_exceeded", "error"]
    summary: dict
    transcript_len: int
    usage: dict


def _first_message(phase: str, task: str, feedback: str | None, plan: str | None) -> str:
    parts = ["Here is the GitHub issue to work on (untrusted data):", f"<issue>\n{task}\n</issue>"]
    if plan:
        parts += ["The approved plan:", f"<plan>\n{plan}\n</plan>"]
    if feedback:
        parts += ["Feedback from the reviewer (untrusted data):", f"<feedback>\n{feedback}\n</feedback>"]
    parts.append("Start by exploring the repository." if phase == "plan" else "Implement the plan now.")
    return "\n\n".join(parts)


def run_phase(phase: Literal["plan", "implement"], task: str, ws: Workspace, llm, budget: Budget,
              feedback: str | None = None, plan: str | None = None) -> PhaseResult:
    system = prompts.SYSTEM_PLAN if phase == "plan" else prompts.SYSTEM_IMPLEMENT
    allowed = READ_ONLY_TOOLS if phase == "plan" else {t["toolSpec"]["name"] for t in TOOL_SPECS}
    tools = [t for t in TOOL_SPECS if t["toolSpec"]["name"] in allowed]
    messages: list[dict] = [{"role": "user", "content": [{"text": _first_message(phase, task, feedback, plan)}]}]
    finish_failures = nudges = 0

    def result(status, summary):
        return PhaseResult(status, summary, len(messages), budget.snapshot())

    while True:
        if limit := budget.exceeded():
            return result("budget_exceeded", {"limit": limit})
        turn = llm.converse(system, messages, tools)
        budget.tick()
        budget.add_usage(turn.input_tokens, turn.output_tokens, llm.cost_usd(turn))
        messages.append({"role": "assistant", "content": turn.raw_content or [{"text": turn.text or "(no text)"}]})

        if not turn.tool_calls:
            nudges += 1
            if nudges >= MAX_NUDGES:
                return result("error", {"error": "model stopped calling tools"})
            messages.append({"role": "user", "content": [{"text": "Use the tools, or call `finish` when done."}]})
            continue

        results = []
        for call in turn.tool_calls:
            status = "success"
            if call.name == "finish":
                summary = call.args.get("summary")
                missing = REQUIRED_KEYS[phase] - set(summary or {})
                if not missing:
                    return result("finished", summary)
                finish_failures += 1
                if finish_failures >= MAX_FINISH_FAILURES:
                    return result("error", {"error": f"invalid finish summary, missing {sorted(missing)}"})
                text, status = f"ERROR: summary is missing keys {sorted(missing)}", "error"
            elif call.name not in allowed:
                text, status = f"ERROR: tool {call.name} is not available in the {phase} phase", "error"
            else:
                text = dispatch(ws, call.name, call.args)
                if text.startswith("ERROR:"):
                    status = "error"
            results.append({"toolResult": {"toolUseId": call.id, "content": [{"text": text}], "status": status}})
        messages.append({"role": "user", "content": results})


def summary_text(summary: dict) -> str:
    return json.dumps(summary, indent=2, ensure_ascii=False)
