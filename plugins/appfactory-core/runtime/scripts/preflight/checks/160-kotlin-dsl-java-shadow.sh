#!/usr/bin/env bash
# Fully-qualified java.<subpackage>.<Class> in a Kotlin DSL script shadows the
# Java plugin extension. Import instead.
. "$(dirname "${BASH_SOURCE[0]}")/../lib.sh"

meta() {
    ID="160-kotlin-dsl-java-shadow"
    TITLE="Kotlin DSL scripts import java.* classes rather than fully-qualifying"
    CATCHES="java.net.URI(...) or java.util.Properties() written fully-qualified in
a *.gradle.kts. In a Kotlin DSL script the bare identifier 'java' resolves to
the Java plugin EXTENSION, not the java.* package, so the reference fails to
compile with 'Unresolved reference: net' (or similar). The fix is a top-level
import; this check refuses the fully-qualified form."
    SCOPE="any *.gradle.kts file"
}
meta
ROOT="$(af_root "${1:-}")"

# Slurp mode. Match: NOT preceded by '.' or a word char (to exclude
# sourceSets.*.java.srcDirs and the like), then `java.<sub>.<CapitalizedClass>`.
found=0
while IFS= read -r file; do
    [ -z "$file" ] && continue
    # Line-oriented, so import declarations can be skipped cleanly. A fully-
    # qualified `java.<sub>.<Class>` reference does not wrap across lines in any
    # real Kotlin script -- this is the same pragmatic trade the corpus's
    # line-oriented patterns document, kept honest by the `bug/` fixture.
    matches="$(perl -ne '
        next if /^\s*import\s/;
        next if /^\s*(\/\/|\*|\/\*)/;
        while (m{(?<![.\w])java\.(net|util|io|nio|time|security|math|lang)\.[A-Z]\w+}g) {
            print "line $.: $&\n";
        }
    ' "$file" 2>/dev/null)"
    if [ -n "$matches" ]; then
        while IFS= read -r m; do
            [ -n "$m" ] && fail "$(realpath --relative-to="$ROOT" "$file"): $m -- import the class instead"
        done <<< "$matches"
        found=1
    fi
done < <(find "$ROOT" -type f -name '*.gradle.kts' 2>/dev/null)

[ "$found" -eq 0 ] && pass "$TITLE"
af_exit
