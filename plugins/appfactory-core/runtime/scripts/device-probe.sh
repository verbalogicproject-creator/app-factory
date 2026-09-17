#!/usr/bin/env bash
#
# device-probe -- prove a web-shell app works ON THIS PHONE, with no adb and no PC.
#
#   bash scripts/device-probe.sh [--pkg PKG] [--mount ID] [--no-launch] [--wait-install SECONDS]
#
# WHY NO ADB. Termux, PRoot and every installed app share the phone's loopback. The
# web-shell's debug build runs a command server on 127.0.0.1:$SAG_PORT, so a process
# here reaches it directly; `adb forward` was only ever needed from a separate computer.
# Termux's `am` launches the app (it needs --user 0 or Android refuses with a cross-user
# SecurityException) and `cmd package` resolves the launcher activity. Installing is the
# one step left to the user: `termux-open app-debug.apk` opens the system installer.
#
# WHAT IT CHECKS -- the judging is runtime/bin/device_verdict.py, covered by pytest:
#   health  pageLoaded, zero counted failures, the expected package on the port
#   dom     non-empty mount with non-zero height, WebView attached  (the white screen)
#   bundle  the page loaded the SAME hashed scripts as the tree's index.html (stale install)
#   crash   no uncaught exception since launch (/__sag/crash; Android/data is unreadable
#           from Termux on Android 11+)
#
# WHAT IT CANNOT CHECK: pixels (the user's eyes still confirm the screen), audio output,
# and a release build -- the command server is debug-only by design (preflight 220).
#
# Exit: 0 pass, 1 the app is broken or stale, 2 the environment is missing something.
# A receipt is written to .appfactory/receipts/<utc>-device-probe.json either way.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT" || exit 2

PKG=""; MOUNT="root"; LAUNCH=1; WAIT_INSTALL=0
while [ $# -gt 0 ]; do
    case "$1" in
        --pkg) PKG="$2"; shift 2 ;;
        --mount) MOUNT="$2"; shift 2 ;;
        --no-launch) LAUNCH=0; shift ;;
        --wait-install) WAIT_INSTALL="$2"; shift 2 ;;
        -h|--help) sed -n '3,6p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

VERDICT=""; for c in "$ROOT/.appfactory/bin/device_verdict.py" "$HERE/../bin/device_verdict.py"; do [ -f "$c" ] && { VERDICT="$c"; break; }; done
[ -n "$VERDICT" ] || { echo "no device_verdict.py"; exit 2; }
command -v curl >/dev/null || { echo "no curl"; exit 2; }

# Termux's am/cmd, reachable from PRoot by absolute path.
TERMUX_BIN="${APPFACTORY_TERMUX_BIN:-/data/data/com.termux/files/usr/bin}"
tool() { if [ -x "$TERMUX_BIN/$1" ]; then echo "$TERMUX_BIN/$1"; else command -v "$1" 2>/dev/null; fi; }
AM="$(tool am)"; CMD="$(tool cmd)"; PM="$(tool pm)"

GRADLE_APP="app/build.gradle.kts"
PORT="${APPFACTORY_SAG_PORT:-$(grep -oE 'SAG_PORT",\s*"[0-9]+' "$GRADLE_APP" 2>/dev/null | grep -oE '[0-9]+$' | head -1)}"
PORT="${PORT:-8765}"
if [ -z "$PKG" ]; then
    app_id="$(grep -oE 'applicationId\s*=\s*"[^"]+"' "$GRADLE_APP" 2>/dev/null | sed 's/.*"\(.*\)"/\1/' | head -1)"
    [ -n "$app_id" ] && PKG="$app_id.debug"
fi
[ -n "$PKG" ] || { echo "cannot tell the package: pass --pkg"; exit 2; }
INDEX="$(find app/src/main/assets -maxdepth 2 -name index.html 2>/dev/null | head -1)"
BASE="http://127.0.0.1:$PORT"

installed() { [ -n "$PM" ] && timeout 30 "$PM" list packages 2>/dev/null | tr -d '\r' | grep -qx "package:$PKG"; }

if [ -n "$PM" ] && ! installed; then
    apk="$(find app/build/outputs/apk/debug -name '*.apk' 2>/dev/null | head -1)"
    echo "$PKG is not installed. Install it on this phone:"
    [ -n "$apk" ] && echo "    cp $apk /storage/emulated/0/Download/ && termux-open /storage/emulated/0/Download/$(basename "$apk")"
    if [ "$WAIT_INSTALL" -gt 0 ]; then
        echo "waiting up to ${WAIT_INSTALL}s for the install..."
        end=$((SECONDS + WAIT_INSTALL))
        until installed; do [ $SECONDS -ge $end ] && { echo "not installed after ${WAIT_INSTALL}s"; exit 2; }; sleep 3; done
    else
        exit 2
    fi
fi

LAUNCHED_MS=$(( $(date +%s) * 1000 ))
if [ "$LAUNCH" -eq 1 ]; then
    [ -n "$AM" ] && [ -n "$CMD" ] || { echo "no Termux am/cmd at $TERMUX_BIN (set APPFACTORY_TERMUX_BIN, or open the app yourself and pass --no-launch)"; exit 2; }
    activity="$(timeout 30 "$CMD" package resolve-activity --brief --user 0 "$PKG" 2>/dev/null | tr -d '\r' | tail -1)"
    case "$activity" in */*) ;; *) echo "no launchable activity for $PKG ($activity)"; exit 1 ;; esac
    out="$(timeout 30 "$AM" start --user 0 -W -n "$activity" 2>&1)"
    case "$out" in *Error*|*Exception*) echo "am start failed:"; echo "$out" | head -5; exit 2 ;; esac
    echo "launched $activity"
fi

T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fetch() { curl -s -m "${3:-5}" "$BASE$1" -o "$T/$2" 2>/dev/null || : > "$T/$2"; }

for _ in $(seq 1 30); do
    fetch /__sag/health health.json 2
    grep -q '"pageLoaded":true' "$T/health.json" 2>/dev/null && break
    sleep 1
done
# A page can finish navigating and still be mounting; give the framework a moment.
sleep 2
fetch /__sag/health health.json
fetch "/__sag/dom?mount=$MOUNT" dom.json 8
fetch "/__sag/diagnostics?failures=true" failures.json
fetch /__sag/crash crash.json

args=(judge --health "$T/health.json" --dom "$T/dom.json" --failures "$T/failures.json"
      --crash "$T/crash.json" --expect-pkg "$PKG" --launched-ms "$LAUNCHED_MS")
[ -n "$INDEX" ] && args+=(--expect-index "$INDEX")
result="$(python3 "$VERDICT" "${args[@]}")"; rc=$?
echo "$result"

mkdir -p .appfactory/receipts
receipt=".appfactory/receipts/$(date -u +%Y%m%dT%H%M%SZ)-device-probe.json"
python3 - "$receipt" "$rc" "$PKG" "$T" "$result" <<'PY'
import json, subprocess, sys
path, rc, pkg, tmp, result = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]
def load(n):
    try: return json.load(open(f"{tmp}/{n}"))
    except Exception: return None
def git(*a):
    try: return subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()
    except Exception: return ""
json.dump({"kind": "device-probe", "pkg": pkg, "rc": rc, "tree": {"sha": git("rev-parse", "HEAD"),
           "dirty": bool(git("status", "--porcelain"))}, "verdict": json.loads(result),
           "health": load("health.json"), "dom": load("dom.json")}, open(path, "w"), indent=1)
PY
echo "receipt: $receipt"
[ "$rc" -eq 0 ] && echo "DEVICE PROBE PASS: $PKG renders on this phone" || echo "DEVICE PROBE FAIL: $PKG"
exit "$rc"
