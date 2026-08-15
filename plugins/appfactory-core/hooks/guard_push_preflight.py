#!/usr/bin/env python3
"""Run the vendored preflight before `git push`, and block if it fails.

THE ECONOMIC ARGUMENT
---------------------
Preflight costs about two seconds and needs no JDK and no Android SDK. A CI round
trip costs two to five minutes. Every documented lesson in this pipeline says "never
skip preflight" -- and a sentence in a document is not a mechanism.

This is the single highest-value component in the marketplace, because it is the only
thing that structurally prevents spending a three-minute round trip on a two-second
bug. Not a reminder. The push does not happen.

DELIBERATE NON-BEHAVIOUR
------------------------
- Only `git push`. Not commit, not fetch, not status.
- If no vendored preflight exists, allow. A repo that has not been bootstrapped is
  not a repo this hook has an opinion about.
- If preflight cannot run at all (missing interpreter, unreadable), allow and say so
  on stderr. A guard that blocks work because it broke is worse than no guard.

Exit 0 allows, exit 2 blocks.
"""
import json
import os
import re
import subprocess
import sys


def repo_root(start: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", start, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    if payload.get("tool_name") != "Bash":
        return 0
    cmd = (payload.get("tool_input") or {}).get("command", "")

    # `git push` as an actual command, not the substring inside a commit message.
    if not re.search(r"(^|[;&|]\s*|\s)git\s+(-C\s+\S+\s+)?push\b", cmd):
        return 0

    root = repo_root(payload.get("cwd") or os.getcwd())
    if not root:
        return 0

    preflight = os.path.join(root, "scripts", "preflight.sh")
    if not os.path.isfile(preflight):
        return 0  # Not an appfactory repo; no opinion.

    try:
        result = subprocess.run(
            ["bash", preflight, root],
            capture_output=True, text=True, timeout=180,
        )
    except Exception as e:
        print(f"preflight could not run ({e}); allowing the push", file=sys.stderr)
        return 0

    if result.returncode == 0:
        return 0

    print(
        "BLOCKED: preflight failed, so this push would spend a 2-5 minute CI round trip "
        "on a bug that costs 2 seconds to find.\n\n"
        + (result.stdout or "") + (result.stderr or "") +
        "\nFix the above, or if a finding is genuinely wrong, record a reason in "
        ".appfactory/preflight-ignore -- the reason field is required, because silent "
        "suppression is how check corpora die.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
