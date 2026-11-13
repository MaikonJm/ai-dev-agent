"""GitHub access as a GitHub App: short-lived installation tokens, issues, PRs and git push."""

import subprocess
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import jwt

from agent.redact import redact

PROTECTED = {"main", "master"}
AUTHOR = ("AI Dev Agent", "ai-dev-agent@users.noreply.github.com")


class GitHubApp:
    def __init__(self, app_id: str, private_key_pem: str, installation_id: str, repo: str,
                 http: httpx.Client | None = None, clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.app_id = app_id
        self.private_key_pem = private_key_pem
        self.installation_id = installation_id
        self.repo = repo
        self.http = http or httpx.Client(base_url="https://api.github.com", timeout=30)
        self.clock = clock
        self._token: str | None = None
        self._expires: datetime | None = None

    def _app_jwt(self) -> str:
        now = int(self.clock().timestamp())
        return jwt.encode({"iat": now - 60, "exp": now + 540, "iss": self.app_id}, self.private_key_pem,
                          algorithm="RS256")

    def token(self) -> str:
        if self._token and self._expires and self.clock() < self._expires - timedelta(minutes=5):
            return self._token
        r = self.http.post(f"/app/installations/{self.installation_id}/access_tokens",
                           headers={"Authorization": f"Bearer {self._app_jwt()}",
                                    "Accept": "application/vnd.github+json"})
        r.raise_for_status()
        data = r.json()
        self._token = data["token"]
        self._expires = datetime.strptime(data["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        return self._token

    def _api(self, method: str, path: str, **kwargs) -> dict:
        r = self.http.request(method, path, headers={"Authorization": f"Bearer {self.token()}",
                                                     "Accept": "application/vnd.github+json"}, **kwargs)
        r.raise_for_status()
        return r.json() if r.content else {}

    def issue(self, number: int) -> dict:
        return self._api("GET", f"/repos/{self.repo}/issues/{number}")

    def comment(self, issue: int, body: str) -> None:
        self._api("POST", f"/repos/{self.repo}/issues/{issue}/comments", json={"body": redact(body)})

    def create_pr(self, branch: str, title: str, body: str, base: str = "main") -> str:
        pr = self._api("POST", f"/repos/{self.repo}/pulls",
                       json={"head": branch, "base": base, "title": redact(title), "body": redact(body)})
        return pr["html_url"]

    def _git(self, args: list[str], cwd: Path | None = None) -> str:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(redact(f"git {args[0]} failed: {r.stderr.replace(self._token or '#', '***')}"))
        return r.stdout

    def _remote(self) -> str:
        return f"https://x-access-token:{self.token()}@github.com/{self.repo}.git"

    def clone(self, dest: Path) -> None:
        self._git(["clone", "--depth", "50", self._remote(), str(dest)])

    def push_branch(self, ws_root: Path, branch: str, message: str) -> None:
        if branch.removeprefix("refs/heads/") in PROTECTED:
            raise ValueError(f"refusing to push to protected branch {branch}")
        name, email = AUTHOR
        self._git(["checkout", "-B", branch], cwd=ws_root)
        self._git(["add", "-A"], cwd=ws_root)
        self._git(["-c", f"user.name={name}", "-c", f"user.email={email}", "commit", "-m", message], cwd=ws_root)
        self._git(["push", "--force-with-lease", self._remote(), f"HEAD:refs/heads/{branch}"], cwd=ws_root)


