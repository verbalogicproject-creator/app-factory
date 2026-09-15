#!/usr/bin/env python3
"""Carry android-dev mode into the session, for as long as it is switched on.

WHY A HOOK AND NOT JUST A SKILL
-------------------------------
A skill's body does persist across turns once invoked, but it is a one-way latch: there
is no off switch, it does not survive a restart, and after a compaction only its first
5,000 tokens return inside a shared budget it competes for. A mode you cannot turn off,
and that quietly weakens as the conversation grows, is not a mode.

So the mode is a STATE FILE, and this hook is what reads it. The file lives in the
project (`.claude/appfactory.local.md`), so the mode is a property of the project rather
than of a session, survives a restart, and can be switched off.

THE SPLIT, AND WHY
------------------
The doctrine is ~1,400 tokens. Injecting that on every prompt would be a real tax and
would churn the prompt cache for no benefit, since it never changes.

  SessionStart  -> the FULL doctrine. Fires on startup, resume, clear and compact.
                   `compact` is the important one: it is the only context-injecting
                   event after a compaction, which is exactly when a skill's content
                   would have thinned out.
  UserPromptSubmit -> a short ANCHOR, a few lines. Enough that the mode cannot drift out
                   of attention between the big injections, cheap enough to pay per turn.

A MODE MUST NEVER BREAK A TURN
------------------------------
Every path here returns 0. On UserPromptSubmit an exit code of 2 does not merely block
the tool, it ERASES the user's prompt. Nothing this file does is worth that, so every
exception is swallowed and the turn proceeds without the injection. The guards next door
follow the same rule for the same reason.

Output must be the nested object with `hookEventName` present, or Claude Code discards it
silently -- a bare string works right up until the text happens to begin with `{`.
"""
import json
import os
import sys
import hook_stdin

# Empirical, not documented: additionalContext degrades into a path + preview past about
# 10,000 characters. Stay under it with room to spare.
MAX_CONTEXT_CHARS = 9000

ANCHOR = """android-dev mode is ON for this project.

Android builds go through `bash scripts/local-build.sh` (never a bare ./gradlew), the
version lattice is adopted rather than derived, and only the DEBUG apk is installable
locally. Act on the fast rungs; ask first before a device install, a release build, a tag
or a Play upload. Full doctrine was injected at session start."""


def _state_path(cwd: str) -> str:
    return os.path.join(cwd, ".claude", "appfactory.local.md")


def mode_enabled(cwd: str) -> bool:
    """True when this project's state file says the mode is on.

    Absent file means off, which is the common case and must cost nothing.
    """
    path = _state_path(cwd)
    if not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read(4096)
    except OSError:
        return False
    # Frontmatter is small and hand-editable; a line test beats a YAML dependency here.
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("enabled:"):
            return stripped.split(":", 1)[1].strip().lower() in ("true", "yes", "on")
    return False


def doctrine(plugin_root: str) -> str:
    path = os.path.join(plugin_root, "references", "android-mode.md")
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return ANCHOR  # Better a short anchor than nothing at all.
    if len(text) > MAX_CONTEXT_CHARS:
        text = text[:MAX_CONTEXT_CHARS] + "\n\n[truncated: hook context caps near 10,000 chars]"
    return text


def main() -> int:
    try:
        payload = json.loads(hook_stdin.read_stdin_bounded())
    except Exception:
        return 0

    try:
        event = payload.get("hook_event_name") or "UserPromptSubmit"
        cwd = payload.get("cwd") or os.getcwd()
        if not mode_enabled(cwd):
            return 0

        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )

        if event == "SessionStart":
            context = doctrine(plugin_root)
            out = {
                "hookSpecificOutput": {
                    "hookEventName": event,
                    "additionalContext": context,
                },
                # systemMessage is shown to the USER and never to the model, which is
                # why the mode being on is visible without costing a token.
                "systemMessage": "android-dev mode: ON (appfactory pipeline)",
            }
        else:
            out = {
                "hookSpecificOutput": {
                    "hookEventName": event,
                    "additionalContext": ANCHOR,
                }
            }
        print(json.dumps(out))
    except Exception:
        return 0  # A mode is never worth losing a turn over.
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
