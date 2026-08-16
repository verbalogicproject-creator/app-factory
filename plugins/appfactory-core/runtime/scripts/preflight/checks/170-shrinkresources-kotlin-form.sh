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
found=0
while IFS= read -r file; do
    [ -z "$file" ] && continue
    if grep -qE '\bshrinkResources\b' "$file"; then
        line="$(grep -nE '\bshrinkResources\b' "$file" | head -1)"
        fail "$(realpath --relative-to="$ROOT" "$file"): Groovy-form shrinkResources in a Kotlin DSL script; use isShrinkResources ($line)"
        found=1
    fi
done < <(find "$ROOT" -type f -name '*.gradle.kts' 2>/dev/null)

[ "$found" -eq 0 ] && pass "$TITLE"
af_exit
