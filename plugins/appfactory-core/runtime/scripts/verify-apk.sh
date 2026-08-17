#!/usr/bin/env bash
#
# verify-apk -- assert that a built APK is actually an APK.
#
#   bash scripts/verify-apk.sh <path-to.apk> [--expect-signed]
#
# WHY THIS EXISTS, AND WHY IT IS NOT A PREFLIGHT CHECK
#
# Preflight runs before a build and there is no APK to look at. This runs after one,
# and it answers the question every other rung skips: not "did the build step
# succeed" but "is the artifact it produced a thing a device can install".
#
# THE INCIDENT. On an aarch64 host, aapt2 2.19 packaged a release APK containing dex,
# native libraries and assets -- and no AndroidManifest.xml and no resources.arsc. The
# zip was structurally intact (`unzip -t` reported no errors). Every rung was green:
# R8 ran, the file existed at the expected size, the release workflow passed ten times
# out of ten. AGP's own shrunk resource archive was correct; only the final merge lost
# them. It was found by a human trying to install it on a phone, and the error names
# the manifest:
#
#   INSTALL_PARSE_FAILED_UNEXPECTED_EXCEPTION: Failed to parse ...: AndroidManifest.xml
#
# which reads like a manifest bug and sends the investigation to the wrong file. The
# fix was aapt2 2.20; the lesson is that "the build step exited 0" was never evidence
# the artifact was valid, and nothing in the pipeline distinguished the two.
#
# WHAT THIS PROVES, AND WHAT IT DOES NOT. It proves the container is well-formed and
# parseable, and optionally that it carries a signature a device will accept. It does
# NOT prove the app runs, that the right code is inside, or that R8 kept what it
# needed. The launch smoke and the instrumented rungs answer those. Stating the limit
# is the point: this exists precisely because a narrow check was mistaken for a broad
# one.
#
set -uo pipefail

APK="${1:-}"
EXPECT_SIGNED=0
for arg in "${@:2}"; do
    case "$arg" in
        --expect-signed) EXPECT_SIGNED=1 ;;
        *) printf 'unknown option: %s\n' "$arg" >&2; exit 2 ;;
    esac
done

if [ -z "$APK" ]; then
    printf 'usage: %s <path-to.apk> [--expect-signed]\n' "$(basename "$0")" >&2
    exit 2
fi
if [ ! -f "$APK" ]; then
    printf 'no such APK: %s\n' "$APK" >&2
    exit 2
fi

if [ -t 1 ]; then G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; O=$'\033[0m'
else G=""; R=""; Y=""; O=""; fi

fails=0
ok()   { printf '%sok%s   %s\n' "$G" "$O" "$1"; }
bad()  { printf '%sFAIL%s %s\n' "$R" "$O" "$1"; fails=$((fails + 1)); }
skip() { printf '%sskip%s %s\n' "$Y" "$O" "$1"; }

printf '%s (%s bytes)\n' "$APK" "$(wc -c < "$APK" | tr -d ' ')"

# ── 1. The two entries whose absence started all this ──────────────────────────
#
# Read with python's zipfile rather than `unzip -l`, because the failure mode being
# guarded against produced an archive that `unzip -t` declared clean. The central
# directory is authoritative; a listing filtered through grep is not.
entries="$(python3 - "$APK" <<'PY' 2>/dev/null
import sys, zipfile
try:
    z = zipfile.ZipFile(sys.argv[1])
except Exception as e:
    print("ZIPERROR", e)
    raise SystemExit(0)
names = z.namelist()
print("COUNT", len(names))
for want in ("AndroidManifest.xml", "resources.arsc"):
    print("HAS", want, want in names)
# resources.arsc must be STORED for the platform to mmap it.
for i in z.infolist():
    if i.filename == "resources.arsc":
        print("ARSC_STORED", i.compress_type == zipfile.ZIP_STORED)
PY
)"

if [ -z "$entries" ] || printf '%s' "$entries" | grep -q '^ZIPERROR'; then
    bad "not a readable zip archive -- $(printf '%s' "$entries" | sed -n 's/^ZIPERROR //p')"
else
    ok "readable zip, $(printf '%s' "$entries" | sed -n 's/^COUNT //p') entries"
    for want in AndroidManifest.xml resources.arsc; do
        if printf '%s' "$entries" | grep -q "^HAS $want True"; then
            ok "contains $want"
        else
            bad "MISSING $want -- the device will reject this with INSTALL_PARSE_FAILED_UNEXPECTED_EXCEPTION. Check the aapt2 version (2.19 drops these on the release path; 2.20 does not)."
        fi
    done
    if printf '%s' "$entries" | grep -q '^ARSC_STORED False'; then
        bad "resources.arsc is compressed -- it must be STORED so the platform can mmap it"
    fi
fi

# ── 2. Does the platform's own parser agree ────────────────────────────────────
#
# The zip check above can pass on an archive whose manifest is present but corrupt.
# aapt2 is the tool the packaging pipeline itself uses, so if it cannot read the
# file, no device will.
AAPT2="${AAPT2:-}"
if [ -z "$AAPT2" ]; then
    for c in aapt2 "${ANDROID_HOME:-}/build-tools"/*/aapt2 "${ANDROID_SDK_ROOT:-}/build-tools"/*/aapt2; do
        [ -x "$c" ] && { AAPT2="$c"; break; }
    done
fi
if [ -z "$AAPT2" ] || ! command -v "$AAPT2" >/dev/null 2>&1 && [ ! -x "$AAPT2" ]; then
    # SKIP LOUDLY. A silent pass is indistinguishable from a clean result, which is
    # the failure this whole script exists to prevent.
    skip "aapt2 not found -- set AAPT2=/path/to/aapt2 to enable manifest parsing"
else
    if badging="$("$AAPT2" dump badging "$APK" 2>&1)"; then
        ok "aapt2 parses it: $(printf '%s' "$badging" | sed -n '1s/^package: //p')"
    else
        bad "aapt2 cannot parse it: $(printf '%s' "$badging" | head -1)"
    fi
fi

# ── 3. Signature, only when the caller says one is expected ────────────────────
#
# Not asserted by default: an unsigned release APK is a legitimate local output, and
# failing on it would train people to pass --skip flags.
if [ "$EXPECT_SIGNED" -eq 1 ]; then
    SIGNER="${APKSIGNER:-}"
    if [ -z "$SIGNER" ]; then
        for c in apksigner "${ANDROID_HOME:-}/build-tools"/*/apksigner "${ANDROID_SDK_ROOT:-}/build-tools"/*/apksigner; do
            [ -x "$c" ] && { SIGNER="$c"; break; }
        done
    fi
    if [ -z "$SIGNER" ] || [ ! -x "$SIGNER" ]; then
        skip "apksigner not found -- set APKSIGNER=/path/to/apksigner"
    elif out="$("$SIGNER" verify --print-certs "$APK" 2>&1 | grep -v WARNING)"; then
        ok "signed by: $(printf '%s' "$out" | sed -n 's/^Signer #1 certificate DN: //p')"
        # The certificate is one of exactly three things about an Android app that can
        # never change after the first user installs it, so it is printed, not just
        # checked. A digest in a log is what lets someone later prove which key signed
        # a build that is already on phones.
        printf '%s' "$out" | sed -n 's/^Signer #1 certificate SHA-256 digest: /     cert SHA-256: /p'
    else
        bad "signature does not verify"
    fi
fi

printf '\n'
if [ "$fails" -eq 0 ]; then
    printf '%sAPK verified%s -- container is well-formed and parseable.\n' "$G" "$O"
    printf '     This does NOT prove the app runs, or that R8 kept what it needed.\n'
    exit 0
fi
printf '%sAPK verification found %d problem(s)%s\n' "$R" "$fails" "$O"
exit 1
