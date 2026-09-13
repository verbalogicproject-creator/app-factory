"""cmdparse: does a shell command INVOKE a thing, or merely mention it.

The enumeration is the point. Each group below is a form the substring match got wrong,
or a form the fix must not break while fixing the others.
"""
import pytest

from tests.conftest import load_module, HOOKS

cmdparse = load_module("cmdparse", HOOKS / "cmdparse.py")

GH = ["gh", "run", "list"]
PHRASE = "gh run " + "list"  # split so this file cannot trip the guard it tests


# ── split_segments: quotes bound a segment, separators end one ────────────────

@pytest.mark.parametrize("command,expected", [
    ("echo a && echo b", ["echo a", "echo b"]),
    ("echo a; echo b", ["echo a", "echo b"]),
    ("echo a | grep b", ["echo a", "grep b"]),
    ("echo a || echo b", ["echo a", "echo b"]),
    ("echo a\necho b", ["echo a", "echo b"]),
])
def test_separators_split(command, expected):
    assert cmdparse.split_segments(command) == expected


@pytest.mark.parametrize("command", [
    'echo "a && b"',
    "echo 'a; b'",
    'echo "a | b"',
])
def test_separators_inside_quotes_do_not_split(command):
    """The bug in one line: a naive regex split treats quoted operators as real ones."""
    assert len(cmdparse.split_segments(command)) == 1


def test_escaped_separator_does_not_split():
    assert len(cmdparse.split_segments(r"echo a \&\& b")) == 1


# ── invocations: consecutive tokens at a command position ─────────────────────

@pytest.mark.parametrize("command", [
    PHRASE,
    f"{PHRASE} --limit 1",
    f"echo hi && {PHRASE}",
    f"echo hi; {PHRASE} --limit 1",
    f"sudo {PHRASE}",
    f"GH_TOKEN=x {PHRASE}",
    f"env GH_TOKEN=x {PHRASE}",
    f"time {PHRASE}",
    f'bash -c "{PHRASE} --limit 1"',
    f"eval {PHRASE}",
])
def test_real_invocations_are_found(command):
    assert cmdparse.invocations(command, GH), command


@pytest.mark.parametrize("command", [
    f"sed -i 's/{PHRASE}/x/' f.py",
    f'echo "{PHRASE}"',
    f"grep -n '{PHRASE}' guard.py",
    f"cat notes/{PHRASE}-incident.md",
    f"python3 -c \"print('{PHRASE}')\"",
    "gh run view 123",
    "gh pr list",
    "git status",
])
def test_mentions_are_not_invocations(command):
    assert cmdparse.invocations(command, GH) == [], command


def test_unparseable_segment_yields_nothing_rather_than_raising():
    """A guard that cannot read a command must not block it."""
    assert cmdparse.invocations('echo "unterminated', GH) == []


def test_wrapper_recursion_is_bounded():
    nested = f'bash -c "bash -c \\"bash -c \\\\\\"bash -c {PHRASE}\\\\\\"\\""'
    cmdparse.invocations(nested, GH)  # must return, not recurse forever


# ── git_subcommand: the flags-before-subcommand problem ───────────────────────

@pytest.mark.parametrize("command,expected", [
    ("git push", "push"),
    ("git push origin main", "push"),
    ("git -C /tmp/x push", "push"),
    ("git -c user.name=x push", "push"),
    ("git --git-dir /tmp/.git push", "push"),
    ("git commit -m 'wip'", "commit"),
    ("git status", "status"),
    ("echo hi", None),
])
def test_git_subcommand(command, expected):
    assert cmdparse.git_subcommand(cmdparse.tokenize(command)) == expected


def test_commit_message_mentioning_push_is_not_a_push():
    """The false positive this repo carried as an xfail: a commit message is data."""
    assert cmdparse.git_invocations("git commit -m 'fix: git push later'", "push") == []
    assert cmdparse.git_invocations('git commit -m "git push"', "push") == []


@pytest.mark.parametrize("command", [
    "git push",
    "git push --force-with-lease",
    "git -C /tmp/other push",
    "cd /tmp/other && git push",
    "echo hi; git push",
    'bash -c "git push"',
])
def test_real_pushes_are_found(command):
    assert cmdparse.git_invocations(command, "push"), command


@pytest.mark.parametrize("command", [
    "git pushd",
    "git status",
    "echo 'git push'",
    "grep -r 'git push' docs/",
])
def test_non_pushes_are_not_found(command):
    assert cmdparse.git_invocations(command, "push") == [], command
