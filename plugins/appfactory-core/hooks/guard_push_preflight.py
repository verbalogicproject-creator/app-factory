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

WHICH REPO GETS PREFLIGHT'D
----------------------------
The blind spot this hook used to have: it resolved the repo from payload["cwd"]
only, so `git -C <repoB> push` and `cd <repoB> && git push` (issued while cwd was
still repoA) ran repoA's preflight -- or none at all if repoA had none -- instead
of repoB's, the one actually being pushed. `target_dir()` now inspects the same
command segment for a `-C <path>` on the git invocation, or a `cd <path>` segment
earlier in the same compound command (`&&`, `;`, `|`, or newline separated),
before falling back to cwd.

Forms this guard still cannot see:
- `git push` invoked from inside a heredoc, an `eval "$(...)"`, or a variable
  holding the command (`cmd="git push"; $cmd`) -- the guard only pattern-matches
  the literal text of tool_input.command.
- A shell alias or function named `push` that wraps `git push` (or `gp`, etc.).
- `-C` or `cd` targets built from command substitution or shell variables
  (`git -C "$REPO" push`, `cd "$dir" && git push`) -- target_dir() only resolves
  literal paths, not the shell's own variable expansion.
- Multiple `cd`s in the same compound command; only the nearest preceding `cd`
  segment (relative to the push segment) is honoured.

Exit 0 allows, exit 2 blocks.
"""
import json
import os
import re
import subprocess
import sys

PUSH_RE = re.compile(r"git\s+(?:-C\s+(?P<cpath>\S+)\s+)?push\b")
CD_RE = re.compile(r"^\s*cd\s+(?P<cdpath>\S+)")


def repo_root(start: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", start, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def target_dir(command: str, cwd: str) -> str:
    """Resolve the directory `git push` in `command` should preflight.

    Preference order: an explicit `-C <path>` on the push invocation itself,
    else the nearest preceding `cd <path>` segment in the same compound
    command, else `cwd`. Relative paths are resolved against `cwd`.
    """
    segments = re.split(r"[;&|]{1,2}|\n", command)
    cd_dir: str | None = None
    push_dir: str | None = None
    for segment in segments:
        stripped = segment.strip()
        push_match = PUSH_RE.search(stripped)
        if push_match:
            cpath = push_match.group("cpath")
            if cpath:
                push_dir = cpath.strip("'\"")
            elif cd_dir:
                push_dir = cd_dir
            break
        cd_match = CD_RE.match(stripped)
        if cd_match:
            cd_dir = cd_match.group("cdpath").strip("'\"")

    target = push_dir or cwd
    if not os.path.isabs(target):
        target = os.path.join(cwd, target)
    return target


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

    cwd = payload.get("cwd") or os.getcwd()
    root = repo_root(target_dir(cmd, cwd))
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
