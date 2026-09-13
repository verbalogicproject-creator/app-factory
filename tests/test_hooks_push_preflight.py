"""Tests for guard_push_preflight.py: run the vendored preflight before `git push`.

Includes two regression cases for the fixed defect where the hook resolved the
repo from payload["cwd"] only, so `git -C <repoB> push` and `cd <repoB> &&
git push` (cwd = repoA) ran repoA's preflight (or none) instead of repoB's.
"""

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


def test_git_commit_message_fix_git_push_allows(git_repo):
    """Was an xfail. The old regex only required whitespace before `git`, so a commit
    message mentioning a push triggered preflight on a plain commit. cmdparse reads the
    subcommand position, so the message is data now.
    """
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


# ── The push enumeration: mentions vs invocations ─────────────────────────────
#
# The mirror of the blind spots fixed earlier the same day. That guard saw too little
# (a push via `git -C` ran preflight on the wrong tree); this one saw too much.

def test_commit_message_with_double_quotes_allows(git_repo):
    repo = git_repo("repo", preflight_exit=1, preflight_output="FAIL x")
    rc, _, _ = run_hook(SCRIPT, _bash('git commit -m "git push"', repo))
    assert rc == 0


def test_grep_for_the_phrase_allows(git_repo):
    repo = git_repo("repo", preflight_exit=1, preflight_output="FAIL x")
    rc, _, _ = run_hook(SCRIPT, _bash("grep -rn 'git push' docs/", repo))
    assert rc == 0


def test_echo_of_the_phrase_allows(git_repo):
    repo = git_repo("repo", preflight_exit=1, preflight_output="FAIL x")
    rc, _, _ = run_hook(SCRIPT, _bash("echo 'remember to git push'", repo))
    assert rc == 0


def test_sed_rewriting_the_phrase_allows(git_repo):
    repo = git_repo("repo", preflight_exit=1, preflight_output="FAIL x")
    rc, _, _ = run_hook(SCRIPT, _bash("sed -i 's/git push/git pull/' notes.md", repo))
    assert rc == 0


def test_quoted_separator_does_not_fake_a_segment(git_repo):
    """`echo "a && git push"` is one segment and invokes nothing."""
    repo = git_repo("repo", preflight_exit=1, preflight_output="FAIL x")
    rc, _, _ = run_hook(SCRIPT, _bash('echo "a && git push"', repo))
    assert rc == 0


def test_push_inside_bash_dash_c_still_blocks(git_repo):
    """Quoting is not proof of inertness: bash -c executes its argument."""
    repo = git_repo("repo", preflight_exit=1, preflight_output="FAIL x")
    rc, _, err = run_hook(SCRIPT, _bash('bash -c "git push"', repo))
    assert rc == 2 and "BLOCKED" in err


def test_sudo_prefixed_push_still_blocks(git_repo):
    repo = git_repo("repo", preflight_exit=1, preflight_output="FAIL x")
    rc, _, err = run_hook(SCRIPT, _bash("sudo git push", repo))
    assert rc == 2 and "BLOCKED" in err


def test_push_with_global_config_flag_still_blocks(git_repo):
    repo = git_repo("repo", preflight_exit=1, preflight_output="FAIL x")
    rc, _, err = run_hook(SCRIPT, _bash("git -c push.default=simple push", repo))
    assert rc == 2 and "BLOCKED" in err


def test_blocked_message_says_nothing_ran(git_repo):
    """A blocked compound command runs none of its parts. During the session that
    produced these tests, a `cp` backup earlier in a blocked command silently never
    happened, and the absent backup was only discovered when it was needed."""
    repo = git_repo("repo", preflight_exit=1, preflight_output="FAIL x")
    rc, _, err = run_hook(SCRIPT, _bash("cp a a.bak && git push", repo))
    assert rc == 2
    assert "Nothing in this command ran" in err
