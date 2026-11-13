import os

import pytest

from agent.tools import TOOL_SPECS, ToolError, Workspace, dispatch


@pytest.fixture
def ws(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "app.py").write_text("print('hi')\n")
    return Workspace(root)


def test_read_outside_root_refused(ws, tmp_path):
    (tmp_path / "secret.txt").write_text("x")
    os.symlink(tmp_path / "secret.txt", ws.root / "link.txt")
    for bad in ["../secret.txt", "/etc/passwd", "link.txt"]:
        with pytest.raises(ToolError):
            ws.read_file(bad)


def test_write_creates_dirs_inside_root(ws):
    ws.write_file("pkg/new.py", "x = 1\n")
    assert (ws.root / "pkg" / "new.py").read_text() == "x = 1\n"


def test_write_over_limit_refused(tmp_path):
    w = Workspace(tmp_path, max_file_bytes=10)
    with pytest.raises(ToolError):
        w.write_file("big.txt", "x" * 11)


@pytest.mark.parametrize("cmd", ["curl http://x", "pytest; rm -rf /", "bash -c pytest", "pytest && ls",
                                 "pip install requests", "git push", "python -c 1"])
def test_run_command_allowlist_refuses(ws, cmd):
    with pytest.raises(ToolError):
        ws.run_command(cmd)


def test_run_command_allowed_runs_without_shell(ws, monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen.update(argv=argv, **kwargs)

        class R:
            returncode = 0
            stdout = "1 passed"
            stderr = ""
        return R()

    monkeypatch.setattr("agent.tools.subprocess.run", fake_run)
    out = ws.run_command("pytest -q tests")
    assert seen["argv"] == ["pytest", "-q", "tests"]
    assert seen.get("shell", False) is False and seen["timeout"] == 300 and seen["cwd"] == ws.root
    assert "exit code 0" in out and "1 passed" in out


def test_pip_install_only_requirements_files(ws, monkeypatch):
    ok = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})
    monkeypatch.setattr("agent.tools.subprocess.run", lambda argv, **k: ok())
    ws.run_command("pip install -r requirements-dev.txt")
    with pytest.raises(ToolError):
        ws.run_command("pip install -r ../evil.txt")


def test_output_truncated_and_redacted(tmp_path):
    w = Workspace(tmp_path, max_output_chars=50)
    (tmp_path / "f.txt").write_text("account 123456789012 " + "y" * 200)
    out = w.read_file("f.txt")
    assert "<account-id>" in out and "123456789012" not in out
    assert len(out) <= 50 + len("\n...[truncated]")


def test_search_code_uses_fixed_strings(ws):
    (ws.root / "a.py").write_text("total = price * (qty)\n")
    assert "a.py:1" in ws.search_code("(qty)")
    assert ws.search_code("no-such-thing") == "no matches"


def test_list_files_skips_git(ws):
    (ws.root / ".git").mkdir()
    (ws.root / ".git" / "config").write_text("x")
    listing = ws.list_files()
    assert "app.py" in listing and ".git" not in listing


def test_dispatch_returns_error_string(ws):
    assert dispatch(ws, "read_file", {"path": "../x"}).startswith("ERROR:")
    assert dispatch(ws, "unknown_tool", {}).startswith("ERROR:")
    assert "print('hi')" in dispatch(ws, "read_file", {"path": "app.py"})


def test_tool_specs_cover_all_tools():
    names = {t["toolSpec"]["name"] for t in TOOL_SPECS}
    assert names == {"list_files", "read_file", "search_code", "write_file", "run_command", "finish"}
