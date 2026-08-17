#!/usr/bin/env bash
# Kotlin DSL uses isShrinkResources, not shrinkResources.
. "$(dirname "${BASH_SOURCE[0]}")/../lib.sh"

meta() {
    ID="170-shrinkresources-kotlin-form"
    TITLE="shrinkResources uses the Kotlin DSL form (isShrinkResources)"
    CATCHES="shrinkResources = true in a *.gradle.kts file. That is the Groovy DSL
form; the Kotlin DSL form is isShrinkResources = true. The Groovy form compiles
in a .kts as an unresolved reference and preflight has not seen it -- the failure
surfaces on CI, which is the 2-second-versus-2-minute trap preflight exists to
prevent. Called out in the top-level README failure table but never enforced
until now."
    SCOPE="any *.gradle.kts file"
}
meta
ROOT="$(af_root "${1:-}")"

# Case-sensitive is exact: isShrinkResources contains ShrinkResources (capital S),
# never shrinkResources (lowercase s), so \bshrinkResources\b matches only the
# Groovy form without a negative lookbehind.
#
# COMMENTS ARE STRIPPED FIRST, and that is not fussiness. The scaffold's own
# app/build.gradle.kts carries a comment explaining this exact trap --
#   // Kotlin DSL name. The Groovy form is `shrinkResources`, and using it ...
# -- so the check fired on the documentation of the bug it targets, in every project
# this pipeline generated. A regex over source reads comments too, and this corpus has
# now been bitten by that twice: the other was check 020, where a comment naming the
# proguardFiles call opened a match that swallowed the next quoted string.
#
# Comment TEXT is blanked rather than the lines deleted, so the reported line number
# still points at the real source line.
found=0
while IFS= read -r file; do
    [ -z "$file" ] && continue
    stripped="$(perl -0777 -pe 's{/\*.*?\*/}{}gs; s{//[^\n]*}{}g' "$file" 2>/dev/null)"
    if printf '%s' "$stripped" | grep -qE '\bshrinkResources\b'; then
        n="$(printf '%s' "$stripped" | grep -nE '\bshrinkResources\b' | head -1 | cut -d: -f1)"
        text="$(sed -n "${n}p" "$file" | sed 's/^[[:space:]]*//')"
        fail "$(realpath --relative-to="$ROOT" "$file"): Groovy-form shrinkResources in a Kotlin DSL script; use isShrinkResources ($n: $text)"
        found=1
    fi
done < <(af_project_files "$ROOT" '*.gradle.kts')

[ "$found" -eq 0 ] && pass "$TITLE"
af_exit
