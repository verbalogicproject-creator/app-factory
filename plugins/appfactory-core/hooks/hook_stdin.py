"""Read a hook payload from stdin, bounded.

WHY THIS EXISTS
---------------
`json.load(sys.stdin)` reads until EOF and only until EOF. Claude Code hands a
hook its payload on a unix socket, not a pipe that is guaranteed to close, so
when EOF never arrives the hook does not fail -- it waits forever, holding its
end of that pipe.

That is not hypothetical. On 2026-09-15 the statusline fragment in this same
plugin, carrying the identical unbounded read spelled `$(cat)`, wedged PRoot --
the ptrace tracer every process in this container runs under -- into
uninterruptible `D` state at `pipe_fcntl`. A stuck tracer cannot service ptrace
stops, so the entire Claude session and all of its MCP servers froze in
`ptrace_stop` for 15 minutes. Killing the one leaked process chain flipped proot
`D -> R` and the session recovered, which is what proved the direction of cause.

WHY THE REGISTERED `timeout` DOES NOT COVER THIS
-------------------------------------------------
Every hook in hooks.json carries a `timeout`, which makes this look like solved
ground. It is not: that timeout is enforced by the parent Claude process, and in
the one failure that matters the parent is itself what is stuck. Nothing is left
running to enforce it. Observed on the statusline: 697 s of runtime past a "5 s
timeout". A bound that lives inside the process being bounded is the only kind
that holds.

WHY THIS IS NOT THE GUARDS' USUAL BLOCK-ON-DOUBT POSTURE
---------------------------------------------------------
These guards block a tool call when they find a real problem. This module does
the opposite on doubt, deliberately: a timeout returns the bytes already
buffered, not an error, and every caller already parses inside a try/except that
allows on unparseable input. A truncated payload therefore takes the same path an
empty one always did -- the guard allows and says nothing.

That is the right trade here and nowhere else. `guard_push_preflight` allowing one
push it could not inspect costs a CI round trip; a guard that hangs costs the
whole session, MCP servers included, with no diagnostic. The documented posture
already agrees: "a guard that blocks work because it broke is worse than no
guard."

DELIBERATE NON-BEHAVIOUR
------------------------
Stdlib-only and import-cheap on purpose. These hooks run on the system
interpreter with no venv, `mode_inject` runs on every single prompt, and
`guard_run_list` runs before every Bash call -- this sits on the latency path in
front of the model.
"""

from __future__ import annotations

import os
import select
import sys
import time

DEFAULT_TIMEOUT_SECONDS = 2.0
_CHUNK = 65536


def read_stdin_bounded(timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Return stdin's bytes as text, giving up after `timeout` seconds.

    Returns whatever arrived before the deadline. Never raises: a guard that dies
    reading its own input is a guard that blocks every tool call after it.
    """

    try:
        fd = sys.stdin.fileno()
    except (AttributeError, ValueError, OSError):
        # Not a real descriptor -- a StringIO under test, or a closed stdin.
        # There is no socket to wedge on, so the plain read is safe.
        try:
            return sys.stdin.read()
        except Exception:  # noqa: BLE001 -- never block the turn
            return ""

    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            sys.stderr.write(
                f"hook_stdin: stdin did not close within {timeout}s; continuing "
                f"with {sum(len(c) for c in chunks)} byte(s) rather than waiting\n")
            break
        try:
            ready, _, _ = select.select([fd], [], [], remaining)
        except (OSError, ValueError):
            break          # fd went away; whatever we have is what there is
        if not ready:
            continue       # the deadline branch above ends the loop
        try:
            chunk = os.read(fd, _CHUNK)
        except InterruptedError:
            continue
        except OSError:
            break
        if not chunk:
            break          # EOF, the normal path
        chunks.append(chunk)

    return b"".join(chunks).decode("utf-8", "replace")
