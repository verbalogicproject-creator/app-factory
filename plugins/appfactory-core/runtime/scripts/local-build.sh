#!/usr/bin/env bash
#
# local-build -- the local verification ladder, wired.
#
#   bash scripts/local-build.sh [--host proot|termux|auto] [--until STAGE] [--bench]
#                               [--stop-daemons] [--keep-going] [STAGE...]
#
#   stages, in ladder order:  preflight compile unit lint debug verify-apk instrumented device release
#
# Each stage is timed and every run writes a receipt to .appfactory/receipts/ -- a JSON
# record of WHICH tree (sha + dirty flag), WHICH host, and what each stage returned. A
# green run carried forward across a later change is not coverage; the receipt is how
# a claim is tied to the tree it was made about.
#
# THE ORDER IS THE POINT. Every rung catches something no cheaper rung can, and the
# default is to stop at the first failure so the cheapest failing rung is the one you
# read. --keep-going runs them all (for a bench).
#
# HOSTS. `proot` runs Gradle here. `termux` runs the SAME Gradle invocation in native
# Termux over loopback ssh (PRoot is ptrace-based and costs on syscall-heavy work);
# it needs sshd on ${APPFACTORY_SSH_PORT:-8022}, JDK 17 in Termux, and
# APPFACTORY_TERMUX_ROOTFS pointing at this distro's rootfs as Termux sees it
# (proot-distro 5.x: $PREFIX/var/lib/proot-distro/containers/<name>/rootfs), and
# APPFACTORY_SSH_KEY (default ~/.ssh/id_ed25519) authorised in Termux. `auto`
# tries termux and falls back to proot, saying so. The default comes from
# ~/.appfactory/build-host (written after the Phase 0 benchmark), else proot.
#
# Nothing here replaces CI. CI is the only x86_64 build and the only one on a machine
# that is not yours.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
# shellcheck source=toolchain-env.sh
source "$HERE/toolchain-env.sh"

LADDER=""
for c in "$ROOT/.appfactory/bin/ladder.py" "$HERE/../bin/ladder.py"; do
    [ -f "$c" ] && { LADDER="$c"; break; }
done
[ -n "$LADDER" ] || { echo "local-build: ladder.py not found (expected .appfactory/bin or runtime/bin)" >&2; exit 2; }

if [ -t 1 ]; then G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; B=$'\033[1m'; O=$'\033[0m'; else G=""; R=""; Y=""; B=""; O=""; fi
say()  { printf '%s== %s%s\n' "$B" "$1" "$O"; }
ok()   { printf '%sok%s   %s\n' "$G" "$O" "$1"; }
warn() { printf '%swarn%s %s\n' "$Y" "$O" "$1"; }
bad()  { printf '%sFAIL%s %s\n' "$R" "$O" "$1"; }

HOST="${APPFACTORY_BUILD_HOST:-}"
UNTIL=""; KIND="run"; STOP_DAEMONS=0; KEEP_GOING=0; REQ=()
while [ $# -gt 0 ]; do
    case "$1" in
        --host) HOST="$2"; shift 2 ;;
        --until) UNTIL="$2"; shift 2 ;;
        --bench) KIND="bench"; STOP_DAEMONS=1; KEEP_GOING=1; shift ;;
        --stop-daemons) STOP_DAEMONS=1; shift ;;
        --keep-going) KEEP_GOING=1; shift ;;
        -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
        --*) echo "unknown option: $1" >&2; exit 2 ;;
        *) REQ+=("$1"); shift ;;
    esac
done
[ -n "$HOST" ] || HOST="$(cat "$HOME/.appfactory/build-host" 2>/dev/null || true)"
[ -n "$HOST" ] || HOST=proot

if [ ${#REQ[@]} -eq 0 ] && [ -z "$UNTIL" ]; then UNTIL="verify-apk"; fi
mapfile -t STAGES < <(python3 "$LADDER" stages ${UNTIL:+--until "$UNTIL"} "${REQ[@]}") || exit 2

cd "$ROOT" || exit 2

# ── host ─────────────────────────────────────────────────────────────────────
say "host"
af_find_jdk17 || { bad "no JDK 17 -- apt install openjdk-17-jdk (arm64 builds are in the ordinary repos)"; exit 1; }
af_find_sdk   || { bad "no Android SDK -- see docs/LOCAL-BUILDS.md step 2; set ANDROID_HOME"; exit 1; }
export JAVA_HOME="$AF_JDK17" ANDROID_HOME="$AF_SDK"
AAPT2="$(af_aapt2 || true)"
ok "jdk $JAVA_HOME"
ok "sdk $ANDROID_HOME"
[ -n "$AAPT2" ] && ok "aapt2 $AAPT2 ($(af_aapt2_version "$AAPT2"))" || warn "no aapt2 found; badging and the release stage will be limited"

SSH_PORT="${APPFACTORY_SSH_PORT:-8022}"
SSH_KEY="${APPFACTORY_SSH_KEY:-$HOME/.ssh/id_ed25519}"
RFS="${APPFACTORY_TERMUX_ROOTFS:-}"
termux_ok() {
    [ -n "$RFS" ] || return 1
    timeout 10 ssh -i "$SSH_KEY" -p "$SSH_PORT" -o BatchMode=yes -o ConnectTimeout=5 localhost 'command -v java >/dev/null' 2>/dev/null
}
case "$HOST" in
    proot) ;;
    termux) termux_ok || { bad "termux host unreachable (need sshd on :$SSH_PORT, java in Termux, APPFACTORY_TERMUX_ROOTFS)"; exit 1; } ;;
    auto) if termux_ok; then HOST=termux; else warn "termux unreachable; falling back to proot"; HOST=proot; fi ;;
    *) bad "unknown host: $HOST"; exit 2 ;;
esac
ok "gradle host: $HOST"

# local.properties is machine-specific and git-ignored; write it for THIS host's view of the SDK.
if [ "$HOST" = termux ]; then printf 'sdk.dir=%s\n' "$RFS$ANDROID_HOME" > local.properties
else printf 'sdk.dir=%s\n' "$ANDROID_HOME" > local.properties; fi

gradle() {
    if [ "$HOST" = termux ]; then
        # Same tree, seen through the rootfs prefix; a separate GRADLE_USER_HOME unless the
        # operator points both at one (the Phase 0 benchmark decides which).
        local guh="${APPFACTORY_TERMUX_GRADLE_USER_HOME:-$RFS$HOME/.gradle}"
        ssh -i "$SSH_KEY" -p "$SSH_PORT" -o BatchMode=yes localhost \
            "cd '$RFS$ROOT' && export GRADLE_USER_HOME='$guh' JAVA_HOME=\"\$(dirname \"\$(dirname \"\$(readlink -f \"\$(command -v java)\")\")\")\" && sh ./gradlew $*"
    else
        ./gradlew "$@"
    fi
}

if [ "$STOP_DAEMONS" -eq 1 ]; then gradle --stop >/dev/null 2>&1 || true; fi

APP_ID="$(sed -n 's/^[[:space:]]*applicationId[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' app/build.gradle.kts | head -1)"

# ── stages ───────────────────────────────────────────────────────────────────
RESULTS=(); ARTIFACTS=(); FAILED=0

run_preflight() { bash scripts/preflight.sh . ; }
run_compile()   { gradle :app:compileDebugKotlin --stacktrace; }
run_unit() {
    gradle testDebugUnitTest --stacktrace || return 1
    # A suite that cannot fail is worse than none: it turns "untested" into "verified".
    local total=0 n f
    shopt -s nullglob globstar
    for f in app/build/test-results/**/*.xml; do
        n=$(sed -n 's/.*<testsuite[^>]* tests="\([0-9]*\)".*/\1/p' "$f" | head -1)
        total=$(( total + ${n:-0} ))
    done
    shopt -u nullglob globstar
    echo "unit tests executed: $total"
    [ "$total" -gt 0 ] || { bad "0 unit tests ran -- testDebugUnitTest passed vacuously"; return 1; }
}
run_lint()  { gradle lint --stacktrace; }
run_debug() { gradle assembleDebug assembleDebugAndroidTest --stacktrace; }
debug_apk() { find app/build/outputs/apk/debug -name '*.apk' 2>/dev/null | head -1; }
run_verify_apk() {
    local apk; apk="$(debug_apk)"
    [ -n "$apk" ] || { bad "no debug APK under app/build/outputs/apk/debug"; return 1; }
    AAPT2="$AAPT2" bash scripts/verify-apk.sh "$apk" && ARTIFACTS+=("$apk")
}
run_instrumented() { bash scripts/device-instrument.sh; }
# No adb: the user installs the debug APK, Termux launches it, loopback probes it.
run_device() { bash scripts/device-probe.sh --wait-install "${APPFACTORY_INSTALL_WAIT:-180}"; }
run_release() {
    # aapt2 < 2.20 packages a release APK with no manifest and no resources.arsc, silently.
    local v; v="$(af_aapt2_version "${AAPT2:-/nonexistent}" 2>/dev/null || true)"
    if [ -z "$v" ]; then bad "release stage needs a known aapt2 version (found none)"; return 1; fi
    if [ "$(printf '%s\n%s\n' "2.20" "${v%%-*}" | sort -V | head -1)" != "2.20" ]; then
        bad "aapt2 $v is older than 2.20 -- the release path drops AndroidManifest.xml (docs/LOCAL-BUILDS.md §4a)"; return 1
    fi
    gradle assembleRelease bundleRelease --stacktrace || return 1
    local apk; apk="$(find app/build/outputs/apk/release -name '*.apk' 2>/dev/null | head -1)"
    [ -n "$apk" ] || { bad "assembleRelease produced no APK"; return 1; }
    local signed=()
    { [ -f keystore.properties ] || [ -n "${SIGNING_KEYSTORE_PATH:-}" ]; } && signed=(--expect-signed)
    AAPT2="$AAPT2" bash scripts/verify-apk.sh "$apk" "${signed[@]}" || return 1
    ARTIFACTS+=("$apk")
    local map=app/build/outputs/mapping/release/mapping.txt
    [ -f "$map" ] || { bad "$map absent -- minification is off or the build did not run"; return 1; }
    local req=""
    [ -f .appfactory/release/required-classes.txt ] && req="$(grep -vE '^\s*(#|$)' .appfactory/release/required-classes.txt | tr '\n' ' ')"
    # shellcheck disable=SC2086
    python3 .appfactory/bin/verify_mapping.py "$map" app/src/main/AndroidManifest.xml app/src/main "$APP_ID" $req
}

LOGDIR=".appfactory/logs"; mkdir -p "$LOGDIR"
for st in "${STAGES[@]}"; do
    say "$st"
    t0=$(date +%s.%N)
    "run_${st//-/_}" 2>&1 | tee "$LOGDIR/$st.log"; rc=${PIPESTATUS[0]}
    secs=$(python3 -c "import sys;print(round(float(sys.argv[2])-float(sys.argv[1]),1))" "$t0" "$(date +%s.%N)")
    RESULTS+=("$st=$rc=$secs")
    if [ "$rc" -eq 0 ]; then
        ok "$st in ${secs}s"
    else
        bad "$st failed (rc=$rc) after ${secs}s"
        # SURFACE THE DIAGNOSTIC, NOT THE STACK TRACE. A Kotlin failure prints four
        # useful lines and then eighty lines of Gradle internals, and the useful ones
        # scroll away. The generated ci.yml already re-emits these as annotations; the
        # local rung had no equivalent, and a web-shell compile error was nearly read
        # as a Gradle problem because of it.
        #
        # Lowest line number FIRST and only the first few: Kotlin reports one broken
        # import as many errors, and "fixing" a cascade error makes correct code wrong.
        if grep -q '^e: ' "$LOGDIR/$st.log" 2>/dev/null; then
            printf '\n%sfirst errors%s (full log: %s)\n' "$B" "$O" "$LOGDIR/$st.log"
            grep '^e: ' "$LOGDIR/$st.log" | head -5 | sed 's|^e: file://||'
        fi
        FAILED=1; [ "$KEEP_GOING" -eq 1 ] || break
    fi
done

# ── receipt ──────────────────────────────────────────────────────────────────
say "receipt"
stage_args=(); for r in "${RESULTS[@]}"; do stage_args+=(--stage "$r"); done
art_args=();   for a in "${ARTIFACTS[@]}"; do art_args+=(--artifact "$a"); done
wrapper="$(sed -n 's#.*/gradle-\([0-9.]*\)-.*#\1#p' gradle/wrapper/gradle-wrapper.properties 2>/dev/null | head -1)"
receipt="$(python3 "$LADDER" receipt --kind "$KIND" --host "$HOST" --out .appfactory/receipts --tree . \
    --jdk "$JAVA_HOME" --gradle-wrapper "$wrapper" --aapt2 "${AAPT2:+$AAPT2 $(af_aapt2_version "$AAPT2")}" \
    "${stage_args[@]}" "${art_args[@]}")" && ok "$receipt" || warn "no receipt written"

if [ "$FAILED" -eq 0 ]; then
    printf '\n%sladder green%s through %s on %s. This proves what these rungs prove and nothing more;\n' "$G" "$O" "${STAGES[-1]}" "$HOST"
    printf 'CI remains the only x86_64 build and the only one on a machine that is not yours.\n'
    exit 0
fi
printf '\n%sladder red%s -- fix the FIRST failing rung; a later green does not cover an earlier red.\n' "$R" "$O"
exit 1
