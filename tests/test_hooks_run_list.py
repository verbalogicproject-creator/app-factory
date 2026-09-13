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


# ── Over-blocking: the phrase appears but nothing is invoked ──────────────────
#
# Found the expensive way. This guard blocked three consecutive real commands during
# the 2026-09-13 plugin-install session: a sed pattern rewriting the guard's own
# message, a grep for it, and a heredoc writing a receipt that quoted it. A guard that
# fires when nothing is wrong is the mirror of one that stays silent when something is,
# and it costs the same thing -- trust.
#
# Enumerated forms where the phrase is DATA, not a command:

def test_phrase_inside_single_quotes_allows():
    rc, _, _ = run_hook(SCRIPT, _bash("sed -i 's/gh run list/x/' file.py"))
    assert rc == 0


def test_phrase_inside_double_quotes_allows():
    rc, _, _ = run_hook(SCRIPT, _bash('echo "gh run list --limit 1"'))
    assert rc == 0


def test_phrase_as_grep_pattern_allows():
    rc, _, _ = run_hook(SCRIPT, _bash("grep -n 'gh run list' hooks/guard_run_list.py"))
    assert rc == 0


def test_phrase_in_a_longer_quoted_sentence_allows():
    rc, _, _ = run_hook(
        SCRIPT, _bash("""printf '%s' 'the guard blocks gh run list without --commit'""")
    )
    assert rc == 0


def test_phrase_as_part_of_a_path_allows():
    rc, _, _ = run_hook(SCRIPT, _bash("cat notes/gh run list-incident.md"))
    assert rc == 0


# ── ...and the forms where it IS a command and must still block ───────────────

def test_after_and_and_still_blocks():
    rc, _, err = run_hook(SCRIPT, _bash("git push && gh run list --limit 1"))
    assert rc == 2 and "BLOCKED" in err


def test_after_semicolon_still_blocks():
    rc, _, err = run_hook(SCRIPT, _bash("echo hi; gh run list --limit 1"))
    assert rc == 2 and "BLOCKED" in err


def test_leading_env_assignment_still_blocks():
    rc, _, err = run_hook(SCRIPT, _bash("GH_TOKEN=x gh run list --limit 1"))
    assert rc == 2 and "BLOCKED" in err


def test_sudo_prefix_still_blocks():
    rc, _, err = run_hook(SCRIPT, _bash("sudo gh run list --limit 1"))
    assert rc == 2 and "BLOCKED" in err


def test_inside_bash_dash_c_still_blocks():
    """A quoted string that bash WILL execute. Quoting is not proof of inertness."""
    rc, _, err = run_hook(SCRIPT, _bash('bash -c "gh run list --limit 1"'))
    assert rc == 2 and "BLOCKED" in err


def test_blocked_message_says_nothing_ran():
    """A blocked compound command executes NONE of its parts, including the parts
    before the offending one. A backup believed to exist did not, during the same
    session that produced these tests."""
    rc, _, err = run_hook(SCRIPT, _bash("cp a a.bak && gh run list --limit 1"))
    assert rc == 2
    assert "Nothing in this command ran" in err
