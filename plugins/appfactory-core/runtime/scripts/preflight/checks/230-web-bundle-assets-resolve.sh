#!/usr/bin/env bash
# Every asset the bundled page references resolves inside the APK's asset mount.
. "$(dirname "${BASH_SOURCE[0]}")/../lib.sh"

meta() {
    ID="230-web-bundle-assets-resolve"
    TITLE="web bundle references resolve inside assets/web"
    CATCHES="The white screen. A web-shell serves app/src/main/assets/web/ at the root of
https://appassets.androidplatform.net/, so '/assets/index.js' must exist as
assets/web/assets/index.js. When it does not -- a Vite 'base' of '/myapp/', a bundle
copied without its assets/ directory, a stylesheet url() pointing at a font that was
never emitted -- the page loads, onPageFinished fires, the Gradle build is green, every
unit test passes, and the phone shows a blank screen. A wrong asset mount once survived
twenty-one preflight checks, a unit suite and an instrumented test at the same time.

Forms checked (enumerated from what a built bundle actually references):
  <script src>, <link href> (stylesheet, modulepreload, icon, manifest, preload),
  <img src>, <source src>, <audio src>, <video src>, <img srcset> / <source srcset>,
  and url(...) in inline <style> and in every .css file of the bundle -- CSS paths
  resolve relative to the CSS file, HTML paths relative to index.html.
Skipped as not the bundle's: http(s):, protocol-relative //, data:, blob:, mailto:,
javascript:, and #fragments. Query strings and fragments are stripped before lookup.

CANNOT SEE: URLs built at runtime in JavaScript (dynamic import(), fetch, new URL()).
Vite's own chunk imports are relative to the importing module and normally correct;
a hand-built absolute string in JS is invisible here -- that is device-probe's
/__sag/diagnostics territory (it records every failed load on the phone)."
    SCOPE="web-shell apps (app/src/main/assets/web/index.html present)"
}
meta
ROOT="$(af_root "${1:-}")"

WEB="$ROOT/app/src/main/assets/web"
[ -f "$WEB/index.html" ] || { pass "$TITLE (no web bundle)"; af_exit; }
command -v python3 >/dev/null 2>&1 || { note "python3 unavailable; skipping $ID"; af_exit; }

out=$(python3 - "$WEB" <<'PY'
import os, re, sys
from html.parser import HTMLParser

web = os.path.realpath(sys.argv[1])
SKIP = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//|#)")
missing = []

def resolve(ref, base_dir, origin):
    ref = ref.strip().strip("'\"")
    if not ref or SKIP.match(ref):
        return
    path = re.split(r"[?#]", ref, maxsplit=1)[0]
    if not path:
        return
    target = os.path.join(web, path.lstrip("/")) if path.startswith("/") else os.path.join(base_dir, path)
    target = os.path.realpath(target)
    if not (target == web or target.startswith(web + os.sep)):
        missing.append(f"{origin}: '{ref}' escapes the bundle root")
    elif not os.path.isfile(target):
        missing.append(f"{origin}: '{ref}' -> assets/web/{os.path.relpath(target, web)} does not exist")

CSS_URL = re.compile(r"url\(\s*([^)]+?)\s*\)")

class Page(HTMLParser):
    def __init__(self):
        super().__init__(); self.in_style = False
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "style":
            self.in_style = True
        for attr in ("src", "href"):
            if attr in a and a[attr] is not None and (tag != "a" and tag != "base"):
                resolve(a[attr], web, f"index.html <{tag} {attr}>")
        if a.get("srcset"):
            for part in a["srcset"].split(","):
                if part.strip():
                    resolve(part.strip().split()[0], web, f"index.html <{tag} srcset>")
        if a.get("style"):
            for m in CSS_URL.finditer(a["style"]):
                resolve(m.group(1), web, f"index.html <{tag} style>")
    def handle_endtag(self, tag):
        if tag == "style":
            self.in_style = False
    def handle_data(self, data):
        if self.in_style:
            for m in CSS_URL.finditer(data):
                resolve(m.group(1), web, "index.html <style>")

Page().feed(open(os.path.join(web, "index.html"), encoding="utf-8", errors="replace").read())

for root, _, files in os.walk(web):
    for f in files:
        if f.endswith(".css"):
            p = os.path.join(root, f)
            text = open(p, encoding="utf-8", errors="replace").read()
            text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
            for m in CSS_URL.finditer(text):
                resolve(m.group(1), root, os.path.relpath(p, web))

print("\n".join(missing))
PY
)

if [ -n "$out" ]; then
    while IFS= read -r line; do fail "$line"; done <<< "$out"
else
    pass "$TITLE"
fi
af_exit
