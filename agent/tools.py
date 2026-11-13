"""Tools the model may call. Every path stays inside the cloned repository and
only allowlisted commands run, without a shell."""

import shlex
import subprocess
from pathlib import Path

from agent.redact import redact

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "node_modules"}


class ToolError(Exception):
    """A refused or failed tool call; the message goes back to the model."""


class Workspace:
    def __init__(self, root: Path, max_file_bytes: int = 200_000, max_output_chars: int = 12_000):
        self.root = Path(root).resolve()
        self.max_file_bytes = max_file_bytes
        self.max_output_chars = max_output_chars

    def _path(self, path: str) -> Path:
        candidate = (self.root / path).resolve()
        if not candidate.is_relative_to(self.root):
            raise ToolError(f"path outside the repository: {path}")
        return candidate

    def _out(self, text: str) -> str:
        text = redact(text)
        if len(text) > self.max_output_chars:
            return text[: self.max_output_chars] + "\n...[truncated]"
        return text

    def _walk(self, start: Path):
        for p in sorted(start.rglob("*")):
            if any(part in SKIP_DIRS for part in p.relative_to(self.root).parts):
                continue
            if p.is_file():
                yield p

    def list_files(self, path: str = ".") -> str:
        start = self._path(path)
        return self._out("\n".join(str(p.relative_to(self.root)) for p in self._walk(start)) or "(empty)")

    def read_file(self, path: str) -> str:
        p = self._path(path)
        if not p.is_file():
            raise ToolError(f"not a file: {path}")
        if p.stat().st_size > self.max_file_bytes:
            raise ToolError(f"file too large: {path}")
        return self._out(p.read_text(errors="replace"))

    def search_code(self, pattern: str) -> str:
        hits = []
        for p in self._walk(self.root):
            try:
                lines = p.read_text().splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            hits += [f"{p.relative_to(self.root)}:{i}: {line.strip()}" for i, line in enumerate(lines, 1)
                     if pattern in line]
        return self._out("\n".join(hits[:200]) or "no matches")

    def write_file(self, path: str, content: str) -> str:
        if len(content.encode()) > self.max_file_bytes:
            raise ToolError(f"content over {self.max_file_bytes} bytes")
        p = self._path(path)
        if any(part in SKIP_DIRS for part in p.relative_to(self.root).parts):
            raise ToolError(f"writing to {path} is not allowed")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"wrote {len(content)} chars to {path}"

    def _allowed(self, argv: list[str]) -> bool:
        if not argv:
            return False
        if argv[0] in ("pytest", "ruff"):
            return True
        if argv[:2] in (["git", "diff"], ["git", "status"]):
            return True
        if argv[:3] == ["pip", "install", "-r"] and len(argv) == 4:
            req = Path(argv[3])
            return req.parent == Path(".") and req.name.startswith("requirements") and req.suffix == ".txt"
        return False

    def run_command(self, command: str) -> str:
        if any(ch in command for ch in ";&|`$<>\n"):
            raise ToolError("shell operators are not allowed")
        argv = shlex.split(command)
        if not self._allowed(argv):
            raise ToolError(f"command not allowed: {command}. Allowed: pytest, ruff, "
                            "pip install -r requirements*.txt, git diff, git status")
        result = subprocess.run(argv, cwd=self.root, capture_output=True, text=True, timeout=300, shell=False)
        return self._out(f"exit code {result.returncode}\n{result.stdout}\n{result.stderr}".strip())


def _spec(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"toolSpec": {"name": name, "description": description, "inputSchema": {"json": {
        "type": "object", "properties": properties, "required": required}}}}


_S = {"type": "string"}
TOOL_SPECS = [
    _spec("list_files", "List files in the repository (or a sub-directory).", {"path": _S}, []),
    _spec("read_file", "Read a text file from the repository.", {"path": _S}, ["path"]),
    _spec("search_code", "Find lines containing a literal string.", {"pattern": _S}, ["pattern"]),
    _spec("write_file", "Create or overwrite a file with the full new content.",
          {"path": _S, "content": _S}, ["path", "content"]),
    _spec("run_command", "Run one allowed command: pytest, ruff, pip install -r requirements*.txt, "
          "git diff, git status.", {"command": _S}, ["command"]),
    _spec("finish", "Finish the phase with a structured summary.",
          {"summary": {"type": "object"}}, ["summary"]),
]
READ_ONLY_TOOLS = {"list_files", "read_file", "search_code", "finish"}


def dispatch(ws: Workspace, name: str, args: dict) -> str:
    fn = {"list_files": ws.list_files, "read_file": ws.read_file, "search_code": ws.search_code,
          "write_file": ws.write_file, "run_command": ws.run_command}.get(name)
    if fn is None:
        return f"ERROR: unknown tool {name}"
    try:
        return fn(**args)
    except ToolError as exc:
        return f"ERROR: {exc}"
    except (TypeError, OSError, subprocess.TimeoutExpired) as exc:
        return f"ERROR: {type(exc).__name__}: {redact(str(exc))}"
