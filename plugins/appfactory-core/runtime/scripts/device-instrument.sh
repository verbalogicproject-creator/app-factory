#!/usr/bin/env bash
#
# device-instrument -- run the androidTest suite on a PHYSICAL device over adb.
#
#   bash scripts/device-instrument.sh [app.apk] [androidTest.apk]
#
# Defaults to app/build/outputs/apk/{debug,androidTest/debug}/*.apk. Build them FIRST
# (`local-build.sh debug`); do not use `connectedAndroidTest` on an unstable link --
# Gradle compiles for minutes before it looks for a device, and the link dies first.
#
# Five things this encodes, each of which cost real time to learn:
#   1. install BOTH APKs -- a stale app/test pair produced 68 NoSuchMethodError that read
#      exactly like real failures;
#   2. derive the packages from the APKs, not from the applicationId: the debug variant
#      carries applicationIdSuffix ".debug", so the test package is <id>.debug.test;
#   3. zero the animation scales (phones run at 1, Compose's waitForIdle never settles)
#      and RESTORE them on every exit path;
#   4. zero tests is a failure, not a pass;
#   5. crashes may not be in logcat on OEM ROMs -- read dumpsys dropbox on failure.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
# shellcheck source=toolchain-env.sh
source "$HERE/toolchain-env.sh"
cd "$ROOT" || exit 2

LADDER=""; for c in "$ROOT/.appfactory/bin/ladder.py" "$HERE/../bin/ladder.py"; do [ -f "$c" ] && { LADDER="$c"; break; }; done
af_find_sdk >/dev/null 2>&1 || true
ADB="${ADB:-}"
[ -n "$ADB" ] || for c in "${ANDROID_HOME:-}/platform-tools/adb" "$(command -v adb 2>/dev/null)"; do [ -n "$c" ] && [ -x "$c" ] && { ADB="$c"; break; }; done
[ -n "$ADB" ] || { echo "no adb (set ADB= or ANDROID_HOME)"; exit 2; }
AAPT2="$(af_aapt2 || true)"
[ -n "$AAPT2" ] || { echo "no aapt2 to read package names from the APKs"; exit 2; }
RUNNER="${APPFACTORY_TEST_RUNNER:-androidx.test.runner.AndroidJUnitRunner}"

APP_APK="${1:-$(find app/build/outputs/apk/debug -name '*.apk' 2>/dev/null | head -1)}"
TEST_APK="${2:-$(find app/build/outputs/apk/androidTest/debug -name '*.apk' 2>/dev/null | head -1)}"
[ -f "${APP_APK:-}" ]  || { echo "no app APK -- run: bash scripts/local-build.sh debug"; exit 2; }
[ -f "${TEST_APK:-}" ] || { echo "no androidTest APK -- run: bash scripts/local-build.sh debug"; exit 2; }

if [ -n "${APPFACTORY_ADB_PORT:-}" ]; then "$ADB" connect "localhost:$APPFACTORY_ADB_PORT" >/dev/null 2>&1 || true; fi
mapfile -t DEVS < <("$ADB" devices | awk 'NR>1 && $2=="device" {print $1}')
if [ ${#DEVS[@]} -eq 0 ]; then echo "no device: pair once (adb pair localhost:<port> <code>) then set APPFACTORY_ADB_PORT=<connect port>"; exit 1; fi
# The same phone shows up twice when connected by both IP and localhost; prefer localhost.
DEV=""; for d in "${DEVS[@]}"; do case "$d" in localhost:*|127.0.0.1:*) DEV="$d";; esac; done
[ -n "$DEV" ] || DEV="${DEVS[0]}"
A() { "$ADB" -s "$DEV" "$@"; }

pkg_of() { "$AAPT2" dump badging "$1" 2>/dev/null | sed -n "s/^package: name='\([^']*\)'.*/\1/p" | head -1; }
APP_PKG="$(pkg_of "$APP_APK")"; TEST_PKG="$(pkg_of "$TEST_APK")"
[ -n "$APP_PKG" ] && [ -n "$TEST_PKG" ] || { echo "could not read package names from the APKs"; exit 2; }
echo "device $DEV ($(A shell getprop ro.product.model | tr -d '\r') / API $(A shell getprop ro.build.version.sdk | tr -d '\r'))"
echo "app  $APP_PKG  <- $APP_APK"
echo "test $TEST_PKG  <- $TEST_APK"

SCALES=(window_animation_scale transition_animation_scale animator_duration_scale)
restore() { for k in "${SCALES[@]}"; do A shell settings put global "$k" 1 >/dev/null 2>&1 || true; done; }
trap restore EXIT

A install -r -d "$APP_APK"     >/dev/null || { echo "FAIL: app APK would not install"; exit 1; }
A install -r -d -t "$TEST_APK" >/dev/null || { echo "FAIL: test APK would not install"; exit 1; }
for k in "${SCALES[@]}"; do A shell settings put global "$k" 0 >/dev/null; done

LOG="$(mktemp)"
A shell am instrument -w -r "$TEST_PKG/$RUNNER" 2>&1 | tr -d '\r' | tee "$LOG" | grep -E '^(OK|FAILURES|Tests run|INSTRUMENTATION_STATUS: (class|test|stack)=|INSTRUMENTATION_RESULT)' || true

verdict="$(python3 "$LADDER" parse-instrument < "$LOG")"; rc=$?
if [ "$rc" -ne 0 ]; then
    echo "FAIL: $verdict"
    echo "--- dropbox (last crashes; logcat is filtered on some OEM ROMs) ---"
    A shell dumpsys dropbox --print 2>/dev/null | grep -A40 -E "data_app_crash|system_app_crash" | tail -120 || true
    rm -f "$LOG"; exit 1
fi
rm -f "$LOG"
echo "Instrumented: ${verdict}, device $(A shell getprop ro.product.model | tr -d '\r')/$(A shell getprop ro.build.version.sdk | tr -d '\r')"
