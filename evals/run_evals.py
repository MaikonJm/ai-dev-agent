"""Runs known tasks through the real pipeline and scores the PRs with hidden acceptance tests.

    GITHUB_TOKEN=<token with issues and contents on the sandbox repo> \
      python -m evals.run_evals --repo MaikonJm/agent-sandbox-shop --cases evals/cases.yaml

The token is read from the environment only; store it in Parameter Store and export it in the shell.
"""

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
from datetime import date
from pathlib import Path

import yaml

PLAN_MARKER = "Proposed plan"
PR_MARKER = re.compile(r"Pull request opened: (\S+/pull/(\d+))")
USAGE = re.compile(r"(\d+) in / (\d+) out tokens · US\$ ([\d.]+) · (\d+) s")


def load_cases(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text())


def summarize(results: list[dict]) -> dict:
    n = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    costs = [r.get("cost_usd", 0) for r in results]
    return {
        "cases": n,
        "passed": passed,
        "success_rate": passed / n if n else 0.0,
        "mean_cost_usd": sum(costs) / n if n else 0.0,
        "max_cost_usd": max(costs, default=0.0),
        "mean_seconds": sum(r.get("seconds", 0) for r in results) / n if n else 0.0,
    }


class GitHub:  # pragma: no cover - network
    def __init__(self, repo: str, token: str):
        import httpx

        self.repo = repo
        self.http = httpx.Client(base_url="https://api.github.com", timeout=30,
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})

    def call(self, method: str, path: str, **kw):
        r = self.http.request(method, f"/repos/{self.repo}{path}", **kw)
        r.raise_for_status()
        return r.json() if r.content else {}

    def wait_comment(self, issue: int, predicate, timeout: int) -> str | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            for c in self.call("GET", f"/issues/{issue}/comments"):
                if predicate(c["body"]):
                    return c["body"]
            time.sleep(15)
        return None


def _usage(*bodies: str) -> tuple[int, float, int]:
    tokens, cost, seconds = 0, 0.0, 0
    for body in bodies:
        if body and (m := USAGE.search(body)):
            tokens += int(m[1]) + int(m[2])
            cost += float(m[3])
            seconds += int(m[4])
    return tokens, cost, seconds


def run_case(gh: GitHub, case: dict, timeout: int) -> dict:  # pragma: no cover - network
    issue = gh.call("POST", "/issues", json={"title": case["title"], "body": case["body"]})["number"]
    gh.call("POST", f"/issues/{issue}/labels", json={"labels": ["agent"]})
    plan = gh.wait_comment(issue, lambda b: PLAN_MARKER in b, timeout)
    if not plan:
        return {"id": case["id"], "issue": issue, "passed": False, "reason": "no plan"}
    gh.call("POST", f"/issues/{issue}/comments", json={"body": "/approve"})
    done = gh.wait_comment(issue, lambda b: bool(PR_MARKER.search(b)) or b.startswith("❌") or "Stopped" in b,
                           timeout)
    if not done or not (m := PR_MARKER.search(done)):
        return {"id": case["id"], "issue": issue, "passed": False, "reason": (done or "timeout")[:200]}
    pr = gh.call("GET", f"/pulls/{m[2]}")
    tokens, cost, seconds = _usage(plan, pr.get("body", ""))
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "clone", "--depth", "1", "-b", pr["head"]["ref"],
                        f"https://github.com/{gh.repo}.git", tmp], check=True, capture_output=True)
        test = Path(tmp) / case["acceptance_test"]["path"]
        test.write_text(case["acceptance_test"]["content"])
        subprocess.run(["pip", "install", "-q", "-r", "requirements-dev.txt"], cwd=tmp, capture_output=True)
        result = subprocess.run(["pytest", "-q", "tests"], cwd=tmp, capture_output=True, text=True)
    return {"id": case["id"], "issue": issue, "pr": m[1], "passed": result.returncode == 0,
            "tokens": tokens, "cost_usd": cost, "seconds": seconds, "tail": result.stdout[-500:]}


def main() -> None:  # pragma: no cover - network
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="MaikonJm/agent-sandbox-shop")
    parser.add_argument("--cases", default="evals/cases.yaml", type=Path)
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    gh = GitHub(args.repo, os.environ["GITHUB_TOKEN"])
    cases = [c for c in load_cases(args.cases) if not args.only or c["id"] in args.only]
    results = [run_case(gh, c, args.timeout) for c in cases]
    out = Path("evals/results") / f"{date.today()}.json"
    out.write_text(json.dumps({"summary": summarize(results), "results": results}, indent=2))
    print(json.dumps(summarize(results), indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
