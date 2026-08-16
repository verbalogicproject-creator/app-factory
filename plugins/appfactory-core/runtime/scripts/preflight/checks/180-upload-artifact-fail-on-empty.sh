#!/usr/bin/env bash
# Every actions/upload-artifact step sets if-no-files-found: error.
. "$(dirname "${BASH_SOURCE[0]}")/../lib.sh"

meta() {
    ID="180-upload-artifact-fail-on-empty"
    TITLE="every actions/upload-artifact step fails on empty match"
    CATCHES="upload-artifact steps whose path glob matches nothing. The action's
if-no-files-found input defaults to 'warn', so an empty glob succeeds silently
and the job is green with no artifact -- the release step (or the human) finds
out much later, or never. Same class as a debug-signed release: the failure
does not look like a failure. Called out in the top-level README failure table
and enforced here."
    SCOPE="any .github/workflows/*.yml file that uses actions/upload-artifact"
}
meta
ROOT="$(af_root "${1:-}")"

command -v python3 >/dev/null 2>&1 || { note "python3 unavailable; skipping $ID"; af_exit; }
[ -d "$ROOT/.github/workflows" ] || { pass "$TITLE (no workflows)"; af_exit; }

out=$(python3 - "$ROOT" <<'PY' 2>/dev/null
import glob, os, sys
try:
    import yaml
except ImportError:
    print("SKIP"); sys.exit(0)
root = sys.argv[1]
findings = []
for f in sorted(glob.glob(os.path.join(root, '.github/workflows/*.y*ml'))):
    try:
        doc = yaml.safe_load(open(f))
    except Exception:
        continue  # 080 owns the "parses" check; do not double-report
    if not isinstance(doc, dict):
        continue
    for job_name, job in (doc.get('jobs') or {}).items():
        if not isinstance(job, dict):
            continue
        for i, step in enumerate(job.get('steps') or []):
            if not isinstance(step, dict):
                continue
            uses = step.get('uses', '')
            if not (isinstance(uses, str) and uses.startswith('actions/upload-artifact')):
                continue
            with_block = step.get('with') or {}
            value = with_block.get('if-no-files-found')
            if value != 'error':
                shown = 'unset' if value is None else repr(value)
                findings.append(
                    f"{os.path.relpath(f, root)}: job '{job_name}' step {i+1} "
                    f"({uses}) has if-no-files-found={shown}; must be 'error'"
                )
for line in findings:
    print(line)
PY
)

if [ "$out" = "SKIP" ]; then
    note "pyyaml unavailable; $ID did not run"
elif [ -n "$out" ]; then
    while IFS= read -r line; do
        [ -n "$line" ] && fail "$line"
    done <<< "$out"
else
    pass "$TITLE"
fi
af_exit
