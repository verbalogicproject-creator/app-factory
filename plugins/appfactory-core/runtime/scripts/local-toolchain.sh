#!/usr/bin/env bash
#
# local-toolchain -- is a local Android build possible on this machine, and if not, why?
#
#   bash local-toolchain.sh [doctor]
#
# DELIBERATELY A DOCTOR, NOT AN INSTALLER.
#
# It downloads nothing and changes nothing. Every check reports what it found and, on
# failure, the exact remediation -- because the two things that go wrong here both fail
# in ways that name the wrong cause:
#
#   * a build-tools binary of the wrong architecture reports "cannot execute: required
#     file not found", which reads as a missing file rather than a wrong ELF machine
#   * AGP ships its OWN aapt2 and prefers it over the SDK's, so replacing the SDK's
#     leaves you with a working binary that AGP never calls, and a daemon-startup error
#     naming a Maven artifact you have never touched
#
# An installer that got either wrong would leave a half-configured SDK and a misleading
# error. A doctor that names the step is worth more than automation that hides it.
#
# Setup instructions: docs/LOCAL-BUILDS.md
#
set -uo pipefail

G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; O=$'\033[0m'
problems=0

ok()   { printf '%sok%s   %s\n' "$G" "$O" "$1"; }
warn() { printf '%swarn%s %s\n' "$Y" "$O" "$1"; }
bad()  { printf '%sFAIL%s %s\n' "$R" "$O" "$1"; problems=$((problems + 1)); }
fix()  { printf '       -> %s\n' "$1"; }

# ELF e_machine, little-endian, at offset 18. 0x3e = x86_64, 0xb7 = aarch64.
elf_machine() {
    [ -f "$1" ] || { printf 'absent'; return; }
    case "$(head -c 20 "$1" 2>/dev/null | xxd -s 18 -l 2 -p 2>/dev/null)" in
        3e00) printf 'x86_64' ;;
        b700) printf 'aarch64' ;;
        0300) printf 'i386' ;;
        2800) printf 'arm32' ;;
        *)    printf 'unknown' ;;
    esac
}

printf '\n== host ==\n'
HOST_ARCH="$(uname -m)"
ok "arch $HOST_ARCH"

# ── JDK ─────────────────────────────────────────────────────────────────────
# 17 is what AGP 8/9 require. The default `java` on PATH is frequently NEWER and
# that is fine -- what matters is that a 17 exists and JAVA_HOME can point at it.
printf '\n== jdk ==\n'
JDK17=""
for candidate in "${JAVA_HOME:-}" /usr/lib/jvm/java-17-openjdk-* /usr/lib/jvm/*17*; do
    [ -n "$candidate" ] && [ -x "$candidate/bin/java" ] || continue
    if "$candidate/bin/java" -version 2>&1 | grep -q '"17\.'; then
        JDK17="$candidate"; break
    fi
done
if [ -n "$JDK17" ]; then
    ok "JDK 17 at $JDK17"
    [ "${JAVA_HOME:-}" = "$JDK17" ] || fix "export JAVA_HOME=$JDK17"
else
    bad "no JDK 17 found"
    fix "apt install openjdk-17-jdk   # arm64 builds are in the ordinary repos"
fi

# ── SDK ─────────────────────────────────────────────────────────────────────
printf '\n== sdk ==\n'
SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/android-sdk}}"
if [ -d "$SDK" ]; then
    ok "sdk at $SDK"
else
    bad "no SDK at $SDK"
    fix "see docs/LOCAL-BUILDS.md step 2; set ANDROID_HOME"
    printf '\n%s%d problem(s)%s\n' "$R" "$problems" "$O"; exit 1
fi

BT="$(find "$SDK/build-tools" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | sort -V | tail -1)"
if [ -n "$BT" ]; then ok "build-tools $(basename "$BT")"; else bad "no build-tools installed"; fi

find "$SDK/platforms" -maxdepth 1 -name 'android-*' 2>/dev/null | head -1 >/dev/null \
    && ok "platform $(basename "$(find "$SDK/platforms" -maxdepth 1 -name 'android-*' | sort -V | tail -1)")" \
    || bad "no platform installed"

# ── native binaries ─────────────────────────────────────────────────────────
#
# Only these four are native. d8/r8/apksigner/lint are shell wrappers over JARs and
# run on any JVM -- replacing them is unnecessary and would break them.
printf '\n== native build-tools (must match host arch) ==\n'
if [ -n "$BT" ]; then
    for tool in aapt2 aapt zipalign aidl; do
        m="$(elf_machine "$BT/$tool")"
        case "$m" in
            aarch64) [ "$HOST_ARCH" = "aarch64" ] && ok "$tool  $m" || warn "$tool  $m (host is $HOST_ARCH)" ;;
            x86_64)  if [ "$HOST_ARCH" = "x86_64" ]; then ok "$tool  $m"
                     else bad "$tool is $m, host is $HOST_ARCH -- cannot execute"
                          fix "replace with an aarch64 build; docs/LOCAL-BUILDS.md step 3"
                     fi ;;
            absent)  bad "$tool absent from $BT" ;;
            *)       warn "$tool  $m" ;;
        esac
    done

    # JVM wrappers: present and NOT replaced.
    for tool in d8 apksigner; do
        if [ -f "$BT/$tool" ]; then
            head -c 4 "$BT/$tool" | grep -q 'ELF' \
                && warn "$tool is a native binary; upstream ships a JVM wrapper -- did something overwrite it?" \
                || ok "$tool  jvm wrapper"
        fi
    done
fi

# ── the aapt2 that AGP actually uses ────────────────────────────────────────
#
# THE STEP EVERYONE MISSES. AGP downloads aapt2 from Maven and prefers it over the
# SDK's, so a correctly-replaced SDK binary is simply never called.
printf '\n== aapt2 AGP will actually invoke ==\n'
OVERRIDE=""
for props in "$HOME/.gradle/gradle.properties" ./gradle.properties; do
    [ -f "$props" ] || continue
    v="$(grep -E '^[[:space:]]*android\.aapt2FromMavenOverride[[:space:]]*=' "$props" 2>/dev/null \
         | tail -1 | cut -d= -f2- | xargs)"
    [ -n "$v" ] || continue
    OVERRIDE="$v"
    case "$props" in
        ./gradle.properties)
            # An absolute path to one machine's binary, committed to the repo. CI is
            # x86_64; this breaks it for everyone else.
            bad "android.aapt2FromMavenOverride is set in the REPO's gradle.properties"
            fix "move it to ~/.gradle/gradle.properties -- it is machine-specific, and CI is x86_64" ;;
        *)  ok "override set in ~/.gradle/gradle.properties" ;;
    esac
done

if [ -z "$OVERRIDE" ]; then
    if [ "$HOST_ARCH" = "x86_64" ]; then
        ok "no override needed on x86_64"
    else
        bad "android.aapt2FromMavenOverride is not set"
        fix "echo 'android.aapt2FromMavenOverride=$BT/aapt2' >> ~/.gradle/gradle.properties"
        fix "without it AGP uses its own x86_64 aapt2 and processResources fails with"
        fix "  'AAPT2 aapt2-<ver>-linux Daemon #0: Daemon startup failed'"
    fi
else
    m="$(elf_machine "$OVERRIDE")"
    if [ "$m" = "absent" ]; then
        bad "override points at a missing file: $OVERRIDE"
    elif [ "$m" != "$HOST_ARCH" ] && [ "$m" != "unknown" ]; then
        bad "override binary is $m, host is $HOST_ARCH: $OVERRIDE"
    else
        ok "override binary is $m"
        # The check that matters: AGP drives aapt2 in DAEMON mode. A binary that
        # answers `version` and cannot start a daemon fails at the only thing it
        # will ever be asked to do.
        if printf '' | timeout 15 "$OVERRIDE" daemon 2>/dev/null | grep -q 'Ready'; then
            # `aapt2 version` writes to STDERR, not stdout. Redirecting 2>/dev/null --
            # the reflex for a version probe -- captures an empty string and reports a
            # blank version for a binary that is working perfectly.
            ok "daemon mode responds  [$("$OVERRIDE" version 2>&1 | head -1)]"
        else
            bad "aapt2 does not start a daemon -- AGP drives it in daemon mode"
            fix "try a newer aarch64 aapt2; the release TAG is not the aapt2 version"
        fi
    fi
fi

printf '\n'
if [ "$problems" -eq 0 ]; then
    printf '%slocal builds should work%s -- verify with: ./gradlew :app:compileDebugKotlin\n' "$G" "$O"
    printf 'Local rungs are an ADDITION to CI, not a replacement. CI is the only x86_64\n'
    printf 'build and the only one on a machine that is not yours.\n'
    exit 0
fi
printf '%s%d problem(s)%s -- see docs/LOCAL-BUILDS.md\n' "$R" "$problems" "$O"
exit 1
