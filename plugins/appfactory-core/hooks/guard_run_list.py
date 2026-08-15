#!/usr/bin/env python3
"""Deny `gh run list` without --commit.

THE INCIDENT
------------
A fix was pushed, `gh run list --limit 1` was used to find "the" run, and GitHub
returned the PREVIOUS commit's run -- which was still in flight and then went green.
The fix was reported as verified by a run that never compiled it. The only tell was
that the uploaded artifacts were byte-identical to the previous run despite a source
change.

A green tick attached to the wrong commit is worse than a red one: it ends the
investigation instead of starting it.

THE SECOND TRAP
---------------
`--commit` requires the FULL 40-character SHA. A short SHA returns an empty list with
exit 0 and no error, which reads as "the run hasn't appeared yet" and pushes you
straight back to `--limit 1`. So this also rejects a short SHA explicitly rather than
letting it fail silently.

Exit 0 allows, exit 2 blocks with the message on stderr.
"""
import json
import re
import sys

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # Never block on a payload we cannot parse.

    if payload.get("tool_name") != "Bash":
        return 0
    cmd = (payload.get("tool_input") or {}).get("command", "")
    if "gh run list" not in cmd:
        return 0

    # Only inspect the `gh run list` invocations, not the whole compound command.
    for segment in re.split(r"[;&|]{1,2}|\n", cmd):
        if "gh run list" not in segment:
            continue

        if "--commit" not in segment:
            print(
                "BLOCKED: `gh run list` without --commit races the push and can return "
                "the PREVIOUS commit's run.\n"
                "That already happened here once: a fix was reported as verified by a run "
                "that never compiled it.\n\n"
                "Use:  gh run list --commit $(git rev-parse HEAD)\n"
                "Note: the FULL sha. A short one returns an empty list with exit 0 and no error.",
                file=sys.stderr,
            )
            return 2

        # --commit is present; make sure it is not a short SHA.
        m = re.search(r"--commit[=\s]+(\S+)", segment)
        if m:
            value = m.group(1).strip("\"'")
            if "$(" in value or "`" in value or value.startswith("$"):
                continue  # A command substitution; assume rev-parse HEAD.
            if not FULL_SHA.match(value):
                print(
                    f"BLOCKED: --commit {value} is not a full 40-character sha.\n"
                    "gh returns an EMPTY LIST with exit 0 for a short sha -- no error, nothing "
                    "to notice.\n"
                    "That reads as 'no run yet' and sends you back to --limit 1, which is the "
                    "race this guard exists to prevent.\n\n"
                    "Use:  gh run list --commit $(git rev-parse HEAD)",
                    file=sys.stderr,
                )
                return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
