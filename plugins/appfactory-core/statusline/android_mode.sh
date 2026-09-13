#!/usr/bin/env bash
#
# statusline fragment: show that android-dev mode is on.
#
# Claude Code passes the session as JSON on stdin and renders whatever this prints. The
# model never sees it and it costs no tokens, which is exactly what a mode indicator
# should cost -- plan mode is visible for the same reason: a mode you forget is on is
# how you get surprised.
#
# Wire it up in ~/.claude/settings.json:
#
#   "statusLine": { "type": "command", "command": "<this file>", "padding": 0 }
#
# CONFIGURING A STATUSLINE REPLACES the default footer hints ("esc to interrupt"), so
# this prints the directory too rather than leaving the line bare. If you already have a
# statusline, call this from it and append the output instead of replacing it.
set -uo pipefail

payload="$(cat 2>/dev/null || true)"

dir="$(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("")
    raise SystemExit(0)
# workspace.current_dir is the documented field; the older flat key is a fallback.
ws = d.get("workspace") or {}
print(ws.get("current_dir") or d.get("current_dir") or d.get("cwd") or "")
' 2>/dev/null)"

[ -n "$dir" ] || dir="$PWD"

state="$dir/.claude/appfactory.local.md"
mode=""
if [ -f "$state" ] && grep -qiE '^enabled:[[:space:]]*(true|yes|on)[[:space:]]*$' "$state" 2>/dev/null; then
    # green dot, then back to default; keep it short so it survives a narrow terminal
    mode=$'\033[32m●\033[0m android-dev '
fi

printf '%s%s' "$mode" "$(basename "$dir")"
