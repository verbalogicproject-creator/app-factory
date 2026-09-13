#!/usr/bin/env bash
#
# sync-web -- refresh app/src/main/assets/web/ from a freshly built web bundle.
#
#   bash scripts/sync-web.sh <dist-dir>
#
# For a --kind web-shell project only. scaffold.py's --web-dir copies the bundle in
# ONCE, at generation time; this is the day-two version -- run it every time the
# web app rebuilds, so app/src/main/assets/web/ never quietly diverges from the
# actual source of truth for what the page does.
#
# REFUSES ON A SOURCE BUNDLE, one that has never been built. index.html is the one
# file every static-site build (Vite, esbuild, webpack...) actually produces, and
# its absence is the cheapest, earliest signal that <dist-dir> is a source tree
# (e.g. accidentally pointed at src/ instead of dist/) rather than a built one.
#
# DELETES STALE FILES FIRST. A previous bundle's asset that the new build renamed
# or removed (a content-hashed filename is the common case) must not survive in
# assets/web/ -- WebViewAssetLoader would still serve it, and a page loading an
# index.html that references it would 404 on a file this script could have removed.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
DEST="$ROOT/app/src/main/assets/web"

DIST="${1:-}"
if [ -z "$DIST" ]; then
    echo "usage: bash scripts/sync-web.sh <dist-dir>" >&2
    exit 2
fi
DIST="$(cd "$DIST" 2>/dev/null && pwd || true)"
if [ -z "$DIST" ] || [ ! -d "$DIST" ]; then
    echo "sync-web: no such directory: ${1}" >&2
    exit 2
fi
if [ ! -f "$DIST/index.html" ]; then
    echo "sync-web: refusing -- $DIST has no index.html. Point this at a BUILT bundle" \
         "(e.g. dist/ after 'npm run build'), not a source tree." >&2
    exit 2
fi

rm -rf "$DEST"
mkdir -p "$DEST"
if command -v rsync >/dev/null 2>&1; then
    rsync -a "$DIST"/ "$DEST"/
else
    cp -a "$DIST"/. "$DEST"/
fi

FILE_COUNT=$(find "$DEST" -type f | wc -l | tr -d ' ')
TOTAL_SIZE=$(du -sh "$DEST" 2>/dev/null | cut -f1)
echo "sync-web: $FILE_COUNT files, $TOTAL_SIZE -> app/src/main/assets/web/"
