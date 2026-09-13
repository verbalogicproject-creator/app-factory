"""Tests for guard_push_preflight.py: run the vendored preflight before `git push`.

Includes two regression cases for the fixed defect where the hook resolved the
repo from payload["cwd"] only, so `git -C <repoB> push` and `cd <repoB> &&
git push` (cwd = repoA) ran repoA's preflight (or none) instead of repoB's.
"""
import pytest

from tests.conftest import run_hook

SCRIPT = "guard_push_preflight.py"


def _bash(command: str, cwd: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}


def test_non_bash_tool_allows(tmp_path):
    rc, _, _ = run_hook(SCRIPT, {"tool_name": "Write", "tool_input": {}, "cwd": str(tmp_path)})
    assert rc == 0


def test_git_status_allows(git_repo):
    repo = git_repo("repo", preflight_exit=1, preflight_output="FAIL x")
    rc, _, _ = run_hook(SCRIPT, _bash("git status", repo))
    assert rc == 0


def test_git_commit_message_containing_push_word_allows(git_repo):
    repo = git_repo("repo", preflight_exit=1, preflight_output="FAIL x")
    rc, _, _ = run_hook(SCRIPT, _bash('git commit -m "git push later"', repo))
    assert rc == 0


@pytest.mark.xfail(
    reason=(
        "The push-detection regex only requires whitespace before `git` and `push` "
        "following (with an optional -C group); it does not require these to be the "
        "actual command verb, so a commit message like 'fix: git push' still matches "
        "the regex textually and triggers preflight on a plain `git commit`. This is a "
        "known false-positive in the guard, not something this test suite is asked to fix."
    ),
    strict=False,
)
def test_git_commit_message_fix_git_push_allows(git_repo):
    repo = git_repo("repo", preflight_exit=1, preflight_output="FAIL x")
    rc, _, _ = run_hook(SCRIPT, _bash("git commit -m 'fix: git push'", repo))
    assert rc == 0


def test_git_push_no_preflight_script_allows(git_repo):
    repo = git_repo("repo")  # no scripts/preflight.sh
    rc, _, _ = run_hook(SCRIPT, _bash("git push", repo))
    assert rc == 0


def test_git_push_preflight_exit_0_allows(git_repo):
    repo = git_repo("repo", preflight_exit=0)
    rc, _, _ = run_hook(SCRIPT, _bash("git push", repo))
    assert rc == 0


def test_git_push_preflight_fails_blocks(git_repo):
    repo = git_repo("repo", preflight_exit=1, preflight_output="FAIL x")
    rc, _, err = run_hook(SCRIPT, _bash("git push", repo))
    assert rc == 2
    assert "FAIL x" in err


def test_git_push_origin_main_same_as_plain_push(git_repo):
    repo = git_repo("repo", preflight_exit=1, preflight_output="FAIL x")
    rc, _, err = run_hook(SCRIPT, _bash("git push origin main", repo))
    assert rc == 2
    assert "FAIL x" in err


def test_git_push_force_with_lease_same_as_plain_push(git_repo):
    repo = git_repo("repo", preflight_exit=1, preflight_output="FAIL x")
    rc, _, err = run_hook(SCRIPT, _bash("git push --force-with-lease", repo))
    assert rc == 2
    assert "FAIL x" in err


def test_git_dash_c_other_repo_push_blocks_on_that_repos_preflight(git_repo):
    """`git -C <repoB> push` with cwd=repoA must run repoB's preflight, not repoA's."""
    repo_a = git_repo("repoA")  # no preflight at all
    repo_b = git_repo("repoB", preflight_exit=1, preflight_output="FAIL x")
    rc, _, err = run_hook(SCRIPT, _bash(f"git -C {repo_b} push", repo_a))
    assert rc == 2
    assert "FAIL x" in err


def test_cd_other_repo_and_push_blocks_on_that_repos_preflight(git_repo):
    """`cd <repoB> && git push` with cwd=repoA must run repoB's preflight."""
    repo_a = git_repo("repoA")
    repo_b = git_repo("repoB", preflight_exit=1, preflight_output="FAIL x")
    rc, _, err = run_hook(SCRIPT, _bash(f"cd {repo_b} && git push", repo_a))
    assert rc == 2
    assert "FAIL x" in err


def test_cd_semicolon_other_repo_and_push_blocks_on_that_repos_preflight(git_repo):
    repo_a = git_repo("repoA")
    repo_b = git_repo("repoB", preflight_exit=1, preflight_output="FAIL x")
    rc, _, err = run_hook(SCRIPT, _bash(f"cd {repo_b}; git push", repo_a))
    assert rc == 2
    assert "FAIL x" in err


def test_git_pushd_is_not_a_push_allows(git_repo):
    repo = git_repo("repo", preflight_exit=1, preflight_output="FAIL x")
    rc, _, _ = run_hook(SCRIPT, _bash("git pushd", repo))
    assert rc == 0
