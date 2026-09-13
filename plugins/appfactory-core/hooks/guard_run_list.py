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

import cmdparse

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
WORDS = ["gh", "run", "list"]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # Never block on a payload we cannot parse.

    if payload.get("tool_name") != "Bash":
        return 0
    cmd = (payload.get("tool_input") or {}).get("command", "")

    # Token-based, not substring-based. A sed pattern or a quoted sentence MENTIONS
    # the phrase; only consecutive tokens at a command position INVOKE it. Three real
    # commands were blocked by the old substring test on 2026-09-13, none of which ran
    # anything. See cmdparse.py for what this still cannot see.
    for tokens in cmdparse.invocations(cmd, WORDS):
        args = tokens[len(WORDS):]
        commit = None
        for i, tok in enumerate(args):
            if tok == "--commit" and i + 1 < len(args):
                commit = args[i + 1]
                break
            if tok.startswith("--commit="):
                commit = tok.split("=", 1)[1]
                break

        if commit is None:
            print(
                "BLOCKED: `gh run list` without --commit races the push and can return "
                "the PREVIOUS commit's run.\n"
                "That already happened here once: a fix was reported as verified by a run "
                "that never compiled it.\n\n"
                "Use:  gh run list --commit $(git rev-parse HEAD)\n"
                "Note: the FULL sha. A short one returns an empty list with exit 0 and no error.\n\n"
                + cmdparse.NOTHING_RAN,
                file=sys.stderr,
            )
            return 2

        # --commit is present; make sure it is not a short SHA.
        value = commit.strip("\"'")
        if "$(" in value or "`" in value or value.startswith("$"):
            continue  # A command substitution; assume rev-parse HEAD.
        if not FULL_SHA.match(value):
            print(
                f"BLOCKED: --commit {value} is not a full 40-character sha.\n"
                "gh returns an EMPTY LIST with exit 0 for a short sha -- no error, nothing "
                "to notice.\n"
                "That reads as 'no run yet' and sends you back to --limit 1, which is the "
                "race this guard exists to prevent.\n\n"
                "Use:  gh run list --commit $(git rev-parse HEAD)"
                    "\n\n" + cmdparse.NOTHING_RAN,
                file=sys.stderr,
            )
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
