#!/usr/bin/env bash
#
# repo-check -- the checks appfactory needs on ITSELF.
#
#   bash scripts/repo-check.sh
#
# NOT the same thing as scripts/preflight.sh. That one is vendored into generated
# Android projects and checks an app. This one checks the factory: that its corpus is
# self-consistent, that its documentation's claims about itself are true, and that its
# marketplace listing describes software that exists.
#
# WHY THIS EXISTS. appfactory had no CI of its own, and three failures followed from
# exactly that:
#
#   1. "12 checks" survived in six places while 19 were on disk. The number was in
#      README twice more, GETTING-STARTED twice, and a prose sentence about corpus
#      growth -- all asserted, none verified.
#   2. runtime/manifest.sha256 drifted 86 files and 7 checks out of date. Nothing reads
#      it, so nothing noticed. An unverified digest manifest is worse than none: it
#      looks like tamper-evidence.
#   3. marketplace.json advertised an interview, a contract and UNVERIFIED.md for a
#      plugin that was a plugin.json and nothing else. Unlike a stale count, that one
#      is discovered by a user, at first contact, on a promise.
#
# All three are the same disease: an assertion nobody checks. This is the cure, and it
# runs in about two seconds without a JDK, an SDK or a network.
#
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2

if [ -t 1 ]; then G=$'\033[32m'; R=$'\033[31m'; D=$'\033[2m'; O=$'\033[0m'
else G=""; R=""; D=""; O=""; fi

fails=0
ok()   { printf '%sok%s   %s\n' "$G" "$O" "$1"; }
bad()  { printf '%sFAIL%s %s\n' "$R" "$O" "$1"; fails=$((fails + 1)); }
note() { printf '%s     %s%s\n' "$D" "$1" "$O"; }

RUNTIME="plugins/appfactory-core/runtime"
CHECKS="$RUNTIME/scripts/preflight/checks"

# ── 1. Every check detects the bug it claims to catch ──────────────────────────
if bash "$RUNTIME/scripts/preflight/selftest.sh" >/tmp/af-selftest.$$ 2>&1; then
    ok "$(tail -1 /tmp/af-selftest.$$ | sed 's/\x1b\[[0-9;]*m//g')"
else
    bad "preflight selftest failed -- a check does not detect its own bug"
    sed 's/^/     /' /tmp/af-selftest.$$ | tail -12
fi
rm -f /tmp/af-selftest.$$

# ── 2. The documented check count is the real one ──────────────────────────────
#
# The specific rot this repository had. Any prose asserting "<N> check(s)" is compared
# against the corpus; a claim is cheaper to write than to keep true.
ACTUAL="$(find "$CHECKS" -name '[0-9][0-9][0-9]-*.sh' | wc -l | tr -d ' ')"
ACTUAL="$ACTUAL" python3 - <<'PY' || fails=$((fails + 1))
import glob, os, re, sys

actual = int(os.environ["ACTUAL"])

# A BARE number is a claim about the corpus. A QUOTED or BACKTICKED one is a citation
# of what a document used to say, and documents legitimately quote their own history --
# this repository's docs discuss the era when there were 12 checks, and rewriting that
# to 20 would make the sentence false.
#
# The first version of this check had three false positives and every one was the same
# 'nearly right' shape the corpus warns about:
#   "SHA-256 checksum"     -> matched '256 check'; the number is part of a hyphenated token
#   '"12 checks" survived' -> a quotation, not an assertion
#   '7 checks out of date' -> prose about drift, now backticked at the source
#
# So: not preceded by a hyphen or word character, and not opened by a quote or backtick.
CLAIM = re.compile(r'(?<![-\w"`])(\d+)\s+(?:static\s+)?checks?\b(?!\s*(?:out of date|behind))')

drift = 0
for path in ["README.md"] + sorted(glob.glob("docs/*.md")):
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        for m in CLAIM.finditer(line):
            claimed = int(m.group(1))
            if claimed != actual:
                print(f"FAIL {path}:{n} claims {claimed} checks; the corpus has {actual}")
                print(f'      {line.strip()[:100]}')
                drift = 1
if not drift:
    print(f"ok   documented check count matches the corpus ({actual})")
sys.exit(drift)
PY

# ── 3. The runtime digest manifest is current ──────────────────────────────────
#
# Regenerated and compared rather than trusted. A manifest that is merely PRESENT
# proves nothing, which is how this one drifted 86 files without anyone noticing.
if [ -f "$RUNTIME/manifest.sha256" ]; then
    ( cd "$RUNTIME" && find . -type f ! -name manifest.sha256 -print0 \
        | sort -z | xargs -0 sha256sum ) > /tmp/af-manifest.$$ 2>/dev/null
    if diff -q /tmp/af-manifest.$$ "$RUNTIME/manifest.sha256" >/dev/null 2>&1; then
        ok "runtime manifest matches the tree ($(wc -l < "$RUNTIME/manifest.sha256" | tr -d ' ') files)"
    else
        bad "runtime/manifest.sha256 is stale -- regenerate it"
        note "cd $RUNTIME && find . -type f ! -name manifest.sha256 -print0 \\"
        note "  | sort -z | xargs -0 sha256sum > manifest.sha256"
        note "differences: $(diff /tmp/af-manifest.$$ "$RUNTIME/manifest.sha256" | grep -c '^[<>]') line(s)"
    fi
    rm -f /tmp/af-manifest.$$
else
    bad "$RUNTIME/manifest.sha256 is absent"
fi

# ── 4. Every advertised plugin is real ─────────────────────────────────────────
#
# THE ONE THAT COSTS A USER'S TRUST. A marketplace entry is a promise made at first
# contact. A manifest with no skills, hooks, commands or runtime behind it is an empty
# box on a shelf with a description on the front.
python3 - <<'PY' || fails=$((fails + 1))
import json, os, sys
mp = ".claude-plugin/marketplace.json"
try:
    entries = json.load(open(mp)).get("plugins", [])
except Exception as e:
    print(f"FAIL {mp} does not parse: {e}"); sys.exit(1)

bad = 0
for e in entries:
    name, src = e.get("name", "?"), e.get("source", "")
    root = src[2:] if src.startswith("./") else src
    if not os.path.isdir(root):
        print(f"FAIL marketplace advertises '{name}' but {src} does not exist"); bad = 1; continue
    # Substance = anything a user could actually invoke or that changes behaviour.
    substance = []
    for sub in ("skills", "hooks", "commands", "agents", "runtime"):
        p = os.path.join(root, sub)
        if os.path.isdir(p) and any(os.scandir(p)):
            substance.append(sub)
    if not substance:
        print(f"FAIL marketplace advertises '{name}' but {src} has no skills, hooks, "
              f"commands, agents or runtime -- it is a manifest and nothing else")
        bad = 1
    else:
        print(f"ok   plugin '{name}' provides: {', '.join(substance)}")
sys.exit(bad)
PY

# ── 5. Declared licences have a licence ────────────────────────────────────────
if grep -rq '"license"' .claude-plugin/marketplace.json plugins/*/.claude-plugin/plugin.json 2>/dev/null; then
    if [ -f LICENSE ]; then
        ok "a licence is declared and LICENSE is present"
    else
        bad "manifests declare a licence but no LICENSE file exists -- the terms are unenforceable"
    fi
fi

# ── 6. Every JSON and workflow template parses ─────────────────────────────────
json_bad=0
while IFS= read -r f; do
    python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$f" 2>/dev/null \
        || { bad "$f does not parse as JSON"; json_bad=1; }
done < <(find . -name '*.json' -not -path './.git/*' -not -path '*/fixtures/*')
[ "$json_bad" -eq 0 ] && ok "every JSON file parses"

yaml_bad=0
while IFS= read -r f; do
    python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" "$f" 2>/dev/null \
        || { bad "$f does not parse as YAML"; yaml_bad=1; }
done < <(find . -name '*.yml' -o -name '*.yaml' | grep -v '/\.git/' | grep -v '/fixtures/')
[ "$yaml_bad" -eq 0 ] && ok "every workflow template parses as YAML"

# ── 7. Shipped shell is syntactically valid ────────────────────────────────────
sh_bad=0
while IFS= read -r f; do
    bash -n "$f" 2>/dev/null || { bad "$f has a shell syntax error"; sh_bad=1; }
done < <(find . -name '*.sh' -not -path './.git/*' -not -path '*/fixtures/*')
[ "$sh_bad" -eq 0 ] && ok "every shipped shell script parses"

printf '\n'
if [ "$fails" -eq 0 ]; then
    printf '%sRepo check clean%s\n' "$G" "$O"
    exit 0
fi
# Counts FAILING CHECKS, not individual findings -- a check that reports four problems
# increments this once. Said plainly because a number that looks like a finding count
# and is not would be the same species of quiet lie this script exists to catch.
printf '%sRepo check: %d failing check(s)%s -- see the FAIL lines above for each finding.\n' \
    "$R" "$fails" "$O"
exit 1
