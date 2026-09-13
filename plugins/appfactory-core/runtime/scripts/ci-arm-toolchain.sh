#!/usr/bin/env bash
#
# ci-arm-toolchain -- get an Android build moving on ubuntu-24.04-arm.
#
# `ubuntu-24.04-arm` GitHub-hosted runners ship no Android SDK at all (unlike
# `ubuntu-latest`, which preinstalls one). android-actions/setup-android installs
# `sdkmanager` itself (a JVM tool, arch-independent) and then this script uses it
# to pull `platform-tools`, `platforms;android-36` and `build-tools;36.0.0` -- but
# NOT the SDK's own aapt2, because there is no aarch64 aapt2 on Google's Maven at
# all: AGP downloads its aapt2 dependency from Maven and there is no aarch64
# artifact published there for it to find. See docs/LOCAL-BUILDS.md §3-§4a for the
# same story on a local aarch64 machine.
#
# Lzhiyong/android-sdk-tools cross-compiles a static aarch64 aapt2 as a
# workaround. Its release v35.0.2 publishes it self-reporting version
# 2.19-<date> -- a native EXEC binary (no dynamic linker, no INTERP segment) that
# answers `daemon` mode correctly. That is enough for a DEBUG build, where R8 does
# not run. It is NOT enough for a release build: docs/LOCAL-BUILDS.md §4a records
# aapt2 2.19 silently producing a release APK with no AndroidManifest.xml and no
# resources.arsc once isMinifyEnabled + isShrinkResources are both on, while every
# other signal (exit code, file size, zip validity) says the build succeeded. That
# is why this script and the ARM CI job that calls it never touch
# assembleRelease/bundleRelease -- doing so would be a green build over a broken
# artifact, which is the exact failure class this corpus exists to catch, not
# reproduce.
#
# Usage: bash ci-arm-toolchain.sh
#   Installs missing SDK packages via sdkmanager (idempotent -- skips what is
#   already present) and leaves a working aapt2 at .appfactory/tmp/aapt2.
set -euo pipefail

G=$'\033[32m'; R=$'\033[31m'; O=$'\033[0m'
ok()  { printf '%sok%s   %s\n' "$G" "$O" "$1"; }
die() { printf '%sFAIL%s %s\n' "$R" "$O" "$1" >&2; exit 1; }

SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
[ -n "$SDK" ] || die "ANDROID_HOME/ANDROID_SDK_ROOT is not set -- run android-actions/setup-android first"

SDKMANAGER="$(find "$SDK/cmdline-tools" -name sdkmanager 2>/dev/null | sort -V | tail -1)"
[ -n "$SDKMANAGER" ] || die "sdkmanager not found under $SDK/cmdline-tools"

PLATFORM="platforms;android-36"
BUILD_TOOLS="build-tools;36.0.0"

for pkg in "$PLATFORM" "$BUILD_TOOLS"; do
    rel="${pkg//;//}"
    if [ -d "$SDK/$rel" ]; then
        ok "$pkg already installed"
    else
        printf 'installing %s...\n' "$pkg"
        yes | "$SDKMANAGER" --sdk_root="$SDK" "$pkg" >/dev/null
        [ -d "$SDK/$rel" ] || die "$pkg did not install to $SDK/$rel"
        ok "$pkg installed"
    fi
done

# ── vendor an aarch64 aapt2 ──────────────────────────────────────────────────
#
# Pinned by content hash, not by trusting the download: a release asset can be
# re-uploaded under an unchanged tag, and a supply-chain compromise here would
# hand a compromised binary root over every generated app's build.
URL="https://github.com/lzhiyong/android-sdk-tools/releases/download/35.0.2/android-sdk-tools-static-aarch64.zip"
SHA256="db1cea2c4454d5f9c5a802646b2d1cf560b4ee7badbe23e51ab8e1881bb50fc2"

TMP="$PWD/.appfactory/tmp"
mkdir -p "$TMP"
ZIP="$TMP/android-sdk-tools-static-aarch64.zip"

if [ ! -f "$TMP/aapt2" ]; then
    printf 'downloading %s\n' "$URL"
    curl -fL -o "$ZIP" "$URL"

    ACTUAL_SHA256="$(sha256sum "$ZIP" | cut -d' ' -f1)"
    if [ "$ACTUAL_SHA256" != "$SHA256" ]; then
        die "sha256 mismatch for $ZIP: expected $SHA256, got $ACTUAL_SHA256"
    fi
    ok "sha256 verified: $ACTUAL_SHA256"

    unzip -o -q -j "$ZIP" 'build-tools/aapt2' -d "$TMP"
    chmod +x "$TMP/aapt2"
    rm -f "$ZIP"
fi

[ -f "$TMP/aapt2" ] || die "aapt2 not found after extracting the archive"

# ELF e_machine, little-endian, at offset 18. 0xb7 = aarch64, 0x3e = x86_64.
MACHINE="$(head -c 20 "$TMP/aapt2" | xxd -s 18 -l 2 -p)"
[ "$MACHINE" = "b700" ] || die "extracted aapt2 has ELF machine $MACHINE, expected b700 (aarch64)"
ok "aapt2 ELF machine is aarch64 ($MACHINE)"

if ! printf '' | timeout 15 "$TMP/aapt2" daemon 2>/dev/null | grep -q 'Ready'; then
    die "aapt2 did not print Ready in daemon mode -- AGP drives it in daemon mode, a version probe alone would miss this"
fi
ok "aapt2 daemon mode responds Ready"

# `aapt2 version` writes to stderr, not stdout.
printf 'aapt2 version: %s\n' "$("$TMP/aapt2" version 2>&1 | head -1)"
ok "aapt2 ready at $TMP/aapt2"
