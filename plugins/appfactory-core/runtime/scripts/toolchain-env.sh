#!/usr/bin/env bash
#
# toolchain-env -- where the local Android toolchain is, as shell functions.
#
#   source scripts/toolchain-env.sh
#   af_find_jdk17 && af_find_sdk && export JAVA_HOME ANDROID_HOME
#
# Extracted from local-toolchain.sh so the doctor and local-build.sh resolve the SAME
# paths by the SAME rules. Two copies of "where is JDK 17" is how updates-log entry 1
# happened: Gradle auto-detected a javac-less JDK 25 and stopped with an error naming
# the wrong JDK, because nothing exported JAVA_HOME for it.
#
# Every function prints nothing on success and sets a variable; callers decide whether
# absence is fatal. Nothing here downloads or changes anything.

# ELF e_machine, little-endian, at offset 18. 0x3e = x86_64, 0xb7 = aarch64.
af_elf_machine() {
    [ -f "$1" ] || { printf 'absent'; return; }
    case "$(head -c 20 "$1" 2>/dev/null | od -An -tx1 -j18 -N2 2>/dev/null | tr -d ' \n')" in
        3e00) printf 'x86_64' ;;
        b700) printf 'aarch64' ;;
        0300) printf 'i386' ;;
        2800) printf 'arm32' ;;
        *)    printf 'unknown' ;;
    esac
}

# Sets AF_JDK17. Honours JAVA_HOME when it IS a 17; otherwise searches the Debian
# layout and Termux's $PREFIX/opt/openjdk-17. AGP 8/9 need 17; the default `java`
# on PATH is frequently newer, and that is fine.
af_find_jdk17() {
    AF_JDK17=""
    local c
    for c in "${JAVA_HOME:-}" /usr/lib/jvm/java-17-openjdk-* /usr/lib/jvm/*17* \
             /data/data/com.termux/files/usr/opt/openjdk-17 /data/data/com.termux/files/usr/lib/jvm/java-17-openjdk; do
        [ -n "$c" ] && [ -x "$c/bin/java" ] || continue
        if "$c/bin/java" -version 2>&1 | grep -q '"17\.'; then
            AF_JDK17="$c"; JAVA_HOME="$c"; return 0
        fi
    done
    return 1
}

# Sets AF_SDK: ANDROID_HOME, then ANDROID_SDK_ROOT, then ~/android-sdk, then the
# GitHub-runner default. Same order as local-toolchain.sh and release.yml.
af_find_sdk() {
    AF_SDK=""
    local c
    for c in "${ANDROID_HOME:-}" "${ANDROID_SDK_ROOT:-}" "$HOME/android-sdk" /usr/local/lib/android/sdk; do
        [ -n "$c" ] && [ -d "$c/platforms" ] || continue
        AF_SDK="$c"; ANDROID_HOME="$c"; return 0
    done
    return 1
}

# Prints the newest build-tools copy of a tool ($1), or nothing.
af_find_tool() {
    local sdk="${AF_SDK:-${ANDROID_HOME:-}}"
    [ -n "$sdk" ] || return 1
    local bt
    bt="$(find "$sdk/build-tools" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | sort -V | tail -1)"
    [ -n "$bt" ] && [ -x "$bt/$1" ] && printf '%s' "$bt/$1"
}

# Prints the aapt2 AGP will actually invoke: the override from ~/.gradle/gradle.properties
# (machine-local, never the repo's), else nothing. On aarch64 an absent override means
# AGP's own x86_64 aapt2 and a daemon-startup error naming a Maven artifact.
af_aapt2_override() {
    local props="$HOME/.gradle/gradle.properties"
    [ -f "$props" ] || return 1
    grep -E '^[[:space:]]*android\.aapt2FromMavenOverride[[:space:]]*=' "$props" 2>/dev/null \
        | tail -1 | cut -d= -f2- | tr -d '[:space:]'
}

# Prints the aapt2 to use for dump/badging: the override if executable, else build-tools.
af_aapt2() {
    local o
    o="$(af_aapt2_override)"
    if [ -n "$o" ] && [ -x "$o" ]; then printf '%s' "$o"; return 0; fi
    af_find_tool aapt2
}

# `aapt2 version` writes to STDERR. Prints e.g. 2.20-android-16.0.0_r4.
af_aapt2_version() {
    "$1" version 2>&1 | sed -n 's/.*(aapt) \([0-9][^ ]*\).*/\1/p' | head -1
}
