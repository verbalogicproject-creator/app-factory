#!/usr/bin/env bash
#
# statusline fragment: show that android-dev mode is on.
#
# Claude Code passes the session as JSON on stdin and renders whatever this prints. The
# model never sees it and it costs no tokens, which is exactly what a mode indicator
# should cost -- plan mode is visible for the same reason: a mode you forget is on is
# how you get surprised.
#
# Two ways to call it:
#
#   android_mode.sh                 standalone. Parses stdin, prints "<mode> <dirname>".
#                                   Wire directly into ~/.claude/settings.json:
#                                     "statusLine": { "type": "command",
#                                                     "command": "<this file>", "padding": 0 }
#                                   CONFIGURING A STATUSLINE REPLACES the default footer
#                                   hints, so this prints the directory too rather than
#                                   leaving the line bare.
#
#   android_mode.sh --fragment DIR  composition. Prints ONLY the mode indicator, empty
#                                   when off, and reads no stdin -- so a wrapper that has
#                                   already parsed the payload does not pay a second
#                                   python3 startup (~110ms on this device) per render.
#
# Claude Code discards the whole line unless the command exits 0, so every path here does.
set -uo pipefail

fragment=0
dir=""
for arg in "$@"; do
    case "$arg" in
        --fragment) fragment=1 ;;
        *) dir="$arg" ;;
    esac
done

# Only parse stdin when the caller did not already hand us the directory.
if [ -z "$dir" ]; then
    payload="$(cat 2>/dev/null || true)"
    dir="$(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("")
    raise SystemExit(0)
if not isinstance(d, dict):
    print("")
    raise SystemExit(0)
# workspace.current_dir is what the CLI actually sends; the flat keys are fallbacks.
ws = d.get("workspace")
ws = ws if isinstance(ws, dict) else {}
print(ws.get("current_dir") or d.get("cwd") or d.get("current_dir") or "")
' 2>/dev/null)"
fi

[ -n "$dir" ] || dir="$PWD"

state="$dir/.claude/appfactory.local.md"
mode=""
if [ -f "$state" ] && grep -qiE '^enabled:[[:space:]]*(true|yes|on)[[:space:]]*$' "$state" 2>/dev/null; then
    # green dot, then back to default; keep it short so it survives a narrow terminal
    mode=$'\033[32m●\033[0m android-dev'
fi

if [ "$fragment" -eq 1 ]; then
    printf '%s' "$mode"
else
    [ -z "$mode" ] || mode="$mode "
    printf '%s%s' "$mode" "$(basename "$dir")"
fi
exit 0
