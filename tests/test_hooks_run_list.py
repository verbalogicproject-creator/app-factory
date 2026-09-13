"""Tests for guard_run_list.py: deny `gh run list` without a full 40-char --commit sha."""
from tests.conftest import run_hook

SCRIPT = "guard_run_list.py"
FULL_SHA = "a" * 40


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def test_non_bash_tool_allows():
    rc, _, _ = run_hook(SCRIPT, {"tool_name": "Write", "tool_input": {}})
    assert rc == 0


def test_bash_without_gh_run_list_allows():
    rc, _, _ = run_hook(SCRIPT, _bash("git status"))
    assert rc == 0


def test_gh_run_list_limit_blocks():
    rc, _, err = run_hook(SCRIPT, _bash("gh run list --limit 1"))
    assert rc == 2
    assert "BLOCKED" in err


def test_gh_run_list_commit_head_rev_parse_allows():
    rc, _, _ = run_hook(SCRIPT, _bash("gh run list --commit $(git rev-parse HEAD)"))
    assert rc == 0


def test_gh_run_list_commit_short_sha_blocks():
    rc, _, err = run_hook(SCRIPT, _bash("gh run list --commit abc1234"))
    assert rc == 2
    assert "BLOCKED" in err


def test_gh_run_list_commit_full_sha_space_allows():
    rc, _, _ = run_hook(SCRIPT, _bash(f"gh run list --commit {FULL_SHA}"))
    assert rc == 0


def test_gh_run_list_commit_full_sha_equals_allows():
    rc, _, _ = run_hook(SCRIPT, _bash(f"gh run list --commit={FULL_SHA}"))
    assert rc == 0


def test_compound_push_and_run_list_limit_blocks():
    rc, _, err = run_hook(SCRIPT, _bash("git push && gh run list --limit 1"))
    assert rc == 2
    assert "BLOCKED" in err


def test_compound_echo_and_run_list_full_sha_allows():
    rc, _, _ = run_hook(SCRIPT, _bash(f"echo x; gh run list --commit {FULL_SHA}"))
    assert rc == 0


def test_invalid_json_stdin_allows():
    import subprocess
    import sys

    from tests.conftest import HOOKS

    proc = subprocess.run(
        [sys.executable, str(HOOKS / SCRIPT)],
        input="{not valid json",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0
