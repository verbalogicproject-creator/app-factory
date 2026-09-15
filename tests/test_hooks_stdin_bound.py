"""Every hook's stdin read is bounded, so a wedged parent cannot hang the session.

`json.load(sys.stdin)` returns on EOF and only on EOF. Claude Code hands a hook a
unix socket, not a pipe guaranteed to close, so an unbounded read does not fail
when EOF never arrives -- it waits forever holding that pipe, and on 2026-09-15
that wedged PRoot into uninterruptible `D` state and froze a whole session for 15
minutes. See plugins/appfactory-core/hooks/hook_stdin.py.

These cases spawn the real script with a pipe that is deliberately never closed,
because the thing under test is whether the PROCESS exits -- which is invisible
from inside that same process. conftest's `run_hook` cannot express this: it
passes `input=`, which closes stdin and delivers the very EOF being withheld.
`Popen.communicate()` is avoided for the same reason.

Enumerated: all four scripts registered in hooks.json (mode_inject on
UserPromptSubmit + 4 SessionStart matchers, guard_run_list and
guard_push_preflight on PreToolUse Bash, guard_secret_material on
PreToolUse Write|Edit|MultiEdit). The search that proves the list complete is
`grep -l 'read_stdin_bounded' plugins/appfactory-core/hooks/*.py`, which returns
these four and hook_stdin.py itself.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time

import pytest

from tests.conftest import HOOKS

# The bound is 2s; the ceiling leaves room for interpreter startup under PRoot
# (~250ms) while staying far below the "waits forever" it exists to catch.
CEILING = 20.0

HOOK_SCRIPTS = [
    "mode_inject.py",
    "guard_run_list.py",
    "guard_push_preflight.py",
    "guard_secret_material.py",
]

# Benign for all four: not a Write/Edit, and a Bash command that is not `git push`,
# so no guard does real work and the only thing being timed is the read.
PAYLOAD = json.dumps({
    "session_id": "bounded-1",
    "hook_event_name": "PreToolUse",
    "tool_name": "Bash",
    "tool_input": {"command": "ls -la"},
    "cwd": str(HOOKS),
})


def run_with_stdin_held_open(argv: list[str], payload: str):
    """Start argv, write payload, never close stdin. Return (rc, stderr, elapsed)."""
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    started = time.monotonic()
    try:
        proc.stdin.write(payload)
        proc.stdin.flush()
        # No .close() -- that is the whole point.
        try:
            rc = proc.wait(timeout=CEILING)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            pytest.fail(f"{argv[-1]} never exited with stdin held open -- the read is unbounded")
        return rc, proc.stderr.read(), time.monotonic() - started
    finally:
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                stream.close()
            except (OSError, ValueError):
                pass


@pytest.mark.parametrize("script", HOOK_SCRIPTS)
def test_every_hook_exits_when_stdin_never_closes(script):
    rc, stderr, elapsed = run_with_stdin_held_open(
        [sys.executable, str(HOOKS / script)], PAYLOAD)

    assert rc == 0, f"{script} exited {rc}: {stderr}"
    assert elapsed < CEILING, f"{script} took {elapsed:.1f}s"
    assert "did not close" in stderr, (
        f"{script} should say on stderr that it stopped waiting; got: {stderr[:300]}")


@pytest.mark.parametrize("script", HOOK_SCRIPTS)
def test_a_truncated_payload_allows_rather_than_blocks(script):
    """The one place these guards allow on doubt, and it has to stay that way.

    A guard that blocked on a payload it could not parse would deny every tool
    call after a slow render. Allowing one uninspected push costs a CI round
    trip; hanging or blocking the session costs everything.
    """
    rc, _, _ = run_with_stdin_held_open(
        [sys.executable, str(HOOKS / script)], '{"tool_name": "Bash", "tool_inp')

    assert rc == 0, f"{script} blocked on a truncated payload instead of allowing"


@pytest.mark.parametrize("script", HOOK_SCRIPTS)
def test_a_closing_stdin_is_not_delayed_by_the_bound(script):
    """The bound must cost nothing on the path that always worked."""
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, str(HOOKS / script)],
        input=PAYLOAD, capture_output=True, text=True, timeout=CEILING)
    elapsed = time.monotonic() - started

    assert result.returncode == 0, result.stderr
    assert elapsed < 2.0, f"{script} took {elapsed:.1f}s on a closing stdin -- the bound is being waited out"
    assert "did not close" not in result.stderr


def test_the_reader_keeps_what_it_read_when_it_gives_up():
    snippet = (
        f"import sys; sys.path.insert(0, {str(HOOKS)!r});"
        "from hook_stdin import read_stdin_bounded;"
        "sys.stdout.write(str(len(read_stdin_bounded(1.0))))"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", snippet],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        proc.stdin.write(PAYLOAD)
        proc.stdin.flush()
        assert proc.wait(timeout=CEILING) == 0
        # A timeout degrades the payload, it never invents an error or drops what
        # already arrived.
        assert proc.stdout.read().strip() == str(len(PAYLOAD))
        assert "did not close" in proc.stderr.read()
    finally:
        proc.kill()
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                stream.close()
            except (OSError, ValueError):
                pass
