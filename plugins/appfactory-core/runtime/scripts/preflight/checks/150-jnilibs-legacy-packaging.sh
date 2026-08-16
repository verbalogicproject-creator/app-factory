#!/usr/bin/env bash
# Apps with native code must set jniLibs.useLegacyPackaging = true so .so files
# are extracted, not mapped -- otherwise directory-scanning loaders find nothing.
. "$(dirname "${BASH_SOURCE[0]}")/../lib.sh"

meta() {
    ID="150-jnilibs-legacy-packaging"
    TITLE="apps with native libraries set jniLibs.useLegacyPackaging = true"
    CATCHES="AGP defaults packaging.jniLibs.useLegacyPackaging to false when
minSdk >= 23, so .so files ship in the APK but are not extracted. dlopen still
works; anything that scans a directory to load backends (llama.cpp's
ggml_backend_load_all_from_path is the case in point) finds nothing. The app
launches, the engine loads, and the failure is a silent absence of capability
-- exactly the failure class that survives every other rung."
    SCOPE="apps with any jniLibs/ contents, ndkVersion, or externalNativeBuild"
}
meta
ROOT="$(af_root "${1:-}")"

APP_BUILD="$ROOT/app/build.gradle.kts"
[ -f "$APP_BUILD" ] || APP_BUILD="$ROOT/app/build.gradle"
[ -f "$APP_BUILD" ] || { pass "$TITLE (no app build file)"; af_exit; }

# Signal that the app uses native code.
uses_native=0
if [ -n "$(find "$ROOT/app/src" -path '*/jniLibs/*' -type f 2>/dev/null | head -1)" ]; then
    uses_native=1
elif perl -0777 -ne 'exit 0 if /\b(ndkVersion|externalNativeBuild)\b/; exit 1' "$APP_BUILD" 2>/dev/null; then
    uses_native=1
fi

if [ "$uses_native" -eq 0 ]; then
    pass "$TITLE (no native code detected)"
    af_exit
fi

# Require: `jniLibs { ... useLegacyPackaging = true ... }` inside packaging.
# Slurp so the block can span lines. Comments are stripped BEFORE matching --
# a `// TODO: enable jniLibs { useLegacyPackaging = true }` in the source is a
# note, not a setting, and the first version of this check was satisfied by
# exactly that near-miss (see fixtures/150-.../bug-comment-only/).
if perl -0777 -ne '
    s{/\*.*?\*/}{}gs;   # strip /* block */ comments
    s{//[^\n]*}{}g;     # strip // line comments
    exit 0 if /jniLibs\s*\{[^}]*useLegacyPackaging\s*=\s*true[^}]*\}/s;
    exit 1
' "$APP_BUILD" 2>/dev/null; then
    pass "$TITLE"
else
    fail "$(realpath --relative-to="$ROOT" "$APP_BUILD"): app has native code but packaging { jniLibs { useLegacyPackaging = true } } is not set; .so files will not be extracted and directory-scanning loaders will find nothing"
fi
af_exit
