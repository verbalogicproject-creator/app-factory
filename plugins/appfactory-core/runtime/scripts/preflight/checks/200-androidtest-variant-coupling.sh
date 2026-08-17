#!/usr/bin/env bash
# Instrumented tests do not reach into a build-type-specific source set.
. "$(dirname "${BASH_SOURCE[0]}")/../lib.sh"

meta() {
    ID="200-androidtest-variant-coupling"
    TITLE="instrumented tests compile for more than one build type"
    CATCHES="An androidTest source referencing a package that exists only in src/debug
(or only in src/release). The debug suite compiles and passes, so nothing looks wrong --
and the whole instrumented corpus is now silently pinned to one build type.

THE INCIDENT. Two Localmind tests called a ToolProposal fixture that lived in
src/debug/java/.../debug/DebugFixtures.kt. src/debug is not compiled for the release
variant, so the first attempt to run the suite against the minified build died in the
Kotlin compiler:

  e: CapabilityGateTest.kt:155:49 Unresolved reference 'debug'.

WHY IT MATTERS MORE THAN IT LOOKS. That project's build file had recorded, in a long
comment, that connectedReleaseAndroidTest 'HANGS with no output until the 45-minute job
timeout' and concluded that behavioural testing of the minified variant was
unachievable. The conclusion was reasonable from the outside and wrong underneath: the
run could never reach a device, because it never compiled. A coupling like this does not
just break one run, it can retire an entire verification rung on false evidence.

THE FAILURE IS REPORTED IN THE WRONG PLACE. The error names an unresolved reference in a
test file, not 'your fixture is in the wrong source set', so the investigation starts at
the call site rather than at the layout.

WHAT COUNTS. Only packages declared in a build-type source set and NOT also declared in
main are flagged. A package present in main is legitimately visible to every variant, and
flagging it would make this check noise -- which is how check corpora die.

Preview fixtures may absolutely live in src/debug; that is what it is for. A fixture that
TESTS asserts on belongs to the test source set. Duplicating a small builder across the
two is the correct outcome, not a DRY violation to be refactored away."
    SCOPE="projects with app/src/androidTest and a build-type source set"
}
meta
ROOT="$(af_root "${1:-}")"

AT_DIRS=()
for d in "$ROOT"/app/src/androidTest/java "$ROOT"/app/src/androidTest/kotlin; do
    [ -d "$d" ] && AT_DIRS+=("$d")
done
if [ "${#AT_DIRS[@]}" -eq 0 ]; then
    pass "$TITLE (no androidTest sources)"
    af_exit
fi

# Packages declared in a source set. Slurped per-file rather than line-grepped across
# the tree so a `package` inside a string or comment column cannot masquerade as a
# declaration -- the anchored match must start the line.
pkgs_in() {
    local dir sub found=0
    for sub in java kotlin; do
        dir="$ROOT/app/src/$1/$sub"
        [ -d "$dir" ] || continue
        found=1
        grep -rhE '^[[:space:]]*package[[:space:]]+[A-Za-z_]' "$dir" \
            --include='*.kt' --include='*.java' 2>/dev/null \
            | sed -E 's/^[[:space:]]*package[[:space:]]+//; s/[;[:space:]]*$//'
    done
    return $((1 - found))
}

MAIN_PKGS="$(pkgs_in main | sort -u)"

variant_only=""
for variant in debug release; do
    while IFS= read -r p; do
        [ -z "$p" ] && continue
        # Declared in main as well: visible to every variant, so not a coupling.
        printf '%s\n' "$MAIN_PKGS" | grep -qxF "$p" && continue
        variant_only+="$variant $p"$'\n'
    done < <(pkgs_in "$variant" | sort -u)
done

if [ -z "$variant_only" ]; then
    pass "$TITLE (no build-type-only packages)"
    af_exit
fi

found=0
while IFS=' ' read -r variant pkg; do
    [ -z "$pkg" ] && continue
    # Both reference forms the incident produced: an `import`, and a fully-qualified
    # call with no import at all. The second is what Localmind actually had, and a
    # check that only looked for imports would have passed on it.
    hits="$(grep -rlE "(^[[:space:]]*import[[:space:]]+${pkg//./\\.}\.)|(\b${pkg//./\\.}\.[A-Za-z_])" \
        "${AT_DIRS[@]}" --include='*.kt' --include='*.java' 2>/dev/null || true)"
    [ -z "$hits" ] && continue
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        fail "androidTest reads src/$variant: ${f#"$ROOT"/} references '$pkg'"
        found=1
    done <<< "$hits"
done <<< "$variant_only"

if [ "$found" -eq 0 ]; then
    pass "$TITLE"
else
    # Deliberately not interpolating the loop variable: it holds whatever the last
    # iteration read, which is not necessarily the variant just reported.
    note "A build-type source set is not compiled for other variants, so the whole"
    note "instrumented suite is pinned to that build type. Move the fixture into"
    note "androidTest and leave src/debug its own copy for previews."
fi
af_exit
