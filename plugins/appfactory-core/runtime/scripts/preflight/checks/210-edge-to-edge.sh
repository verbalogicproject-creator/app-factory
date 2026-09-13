#!/usr/bin/env bash
# API 36 makes edge-to-edge mandatory and non-opt-out for Compose apps: content
# must be drawn under the system bars, and the app is responsible for insetting it.
. "$(dirname "${BASH_SOURCE[0]}")/../lib.sh"

meta() {
    ID="210-edge-to-edge"
    TITLE="Compose activities call enableEdgeToEdge() when targeting API 35+"
    CATCHES="ANTICIPATED, not an observed incident: this is a guess about the API 36
platform behaviour change, labelled as one.

Starting with targetSdk 35 the platform enforces edge-to-edge display and removed the
opt-out; from targetSdk 36 there is no opt-out at all. A Compose Activity that calls
setContent { ... } without first calling enableEdgeToEdge() (androidx.activity) still
compiles, still launches, and its content is drawn UNDER the status bar and
navigation bar rather than around them -- a launch that looks fine in a screenshot
taken mid-animation and wrong the moment a user looks at the top of the screen.
Nothing else in this corpus reads runtime layout, so nothing else would catch it."
    SCOPE="apps targeting API 35+ (targetSdk >= 35) with a Compose Activity"
}
meta
ROOT="$(af_root "${1:-}")"

APP_BUILD="$ROOT/app/build.gradle.kts"
[ -f "$APP_BUILD" ] || APP_BUILD="$ROOT/app/build.gradle"
[ -f "$APP_BUILD" ] || { pass "$TITLE (no app module)"; af_exit; }

target=$(grep -oE 'targetSdk\s*=\s*[0-9]+' "$APP_BUILD" 2>/dev/null | grep -oE '[0-9]+' | head -1)
if [ -z "$target" ]; then
    if grep -q 'targetSdk\s*=\s*{{' "$APP_BUILD" 2>/dev/null; then
        pass "$TITLE (unrendered template)"
        af_exit
    fi
    pass "$TITLE (no targetSdk declared)"
    af_exit
fi

if [ "$target" -lt 35 ]; then
    pass "$TITLE (targetSdk $target, below the API 35 enforcement floor)"
    af_exit
fi

# Comments are stripped BEFORE matching, for the same reason check 150 strips them:
# a `// TODO: call enableEdgeToEdge()` is a note, not a call, and would otherwise
# satisfy a naive grep. See fixtures/210-edge-to-edge/bug-comment-only/.
strip_comments() { perl -0777 -pe 's{/\*.*?\*/}{}gs; s{//[^\n]*}{}g' "$1" 2>/dev/null; }

has_set_content=0
has_edge_to_edge=0
has_opt_out=0

while IFS= read -r file; do
    [ -z "$file" ] && continue
    stripped="$(strip_comments "$file")"
    printf '%s' "$stripped" | grep -q 'setContent\s*{' && has_set_content=1
    printf '%s' "$stripped" | grep -q 'enableEdgeToEdge\s*(' && has_edge_to_edge=1
done < <(af_project_files "$ROOT" '*.kt')

# Manifest/theme opt-out. It still works through API 35 (removed entirely at 36), so
# it is a NOTE, not a fail: it may be intentional for an app that targets 35 today and
# has not yet done the inset work, and this check should not punish a documented,
# reversible choice the same way it punishes silent absence.
while IFS= read -r file; do
    [ -z "$file" ] && continue
    grep -q 'windowOptOutEdgeToEdgeEnforcement' "$file" 2>/dev/null && has_opt_out=1
done < <(af_project_files "$ROOT" '*.xml')

if [ "$has_opt_out" -eq 1 ]; then
    note "windowOptOutEdgeToEdgeEnforcement is set: edge-to-edge enforcement is opted out for now, and that opt-out is removed entirely at targetSdk 36"
fi

if [ "$has_set_content" -eq 1 ] && [ "$has_edge_to_edge" -eq 0 ]; then
    fail "targetSdk $target requires edge-to-edge; a Compose Activity calls setContent { } but no source calls enableEdgeToEdge() -- content will draw under the status bar and navigation bar"
else
    pass "$TITLE (targetSdk $target)"
fi
af_exit
