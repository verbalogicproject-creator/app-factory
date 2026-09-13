# Plugin roadmap — executed / superseded

**Status: executed / superseded.** This document originally argued through the
plugin-split question. That argument is settled; the decisions below record what was
decided and what was actually done, so the reasoning stays findable without the
now-stale in-progress framing.

## What was decided

One plugin, `appfactory-core`, not four. Four skills inside it:

- `bootstrap` — present.
- `plan` — interview → `.appfactory/contract/`. Planned in v1.0.0, not yet present.
- `verify` — the local ladder: preflight → compile → unit → lint → debug APK →
  verify-apk → on-device instrumented over loopback adb → release. Planned in v1.0.0,
  not yet present.
- `release` — tag → CI → signed APK/AAB → cert pin → Play internal track via Gradle
  Play Publisher. Planned in v1.0.0, not yet present.

This supersedes this document's earlier "Decision 2" (three plugins: fold `-build` into
core, keep `-plan` and `-ui` separate). The one-plugin, four-skill shape is the plan of
record; see the v1.0.0 plan of record for the full reasoning.

## What was done

- `appfactory-plan`, `appfactory-ui`, `appfactory-build` — the three manifest-only stub
  plugins — are deleted (`git rm -r`), not implemented. Their manifests were never real
  and describing them as "scaffolded" was the documentation error this roadmap existed
  to fix.
- Decision 1 (remove stub entries from `marketplace.json`) was already done in
  `8f06ea8` and confirmed still in place: `marketplace.json` lists only
  `appfactory-core`.

## Cross-cutting work

1. **A check that docs match the corpus.** Done — `scripts/repo-check.sh` and
   `.github/workflows/ci.yml`.
2. **Verify `manifest.sha256`.** Done — `scripts/repo-check.sh` verifies the digest.
3. **A fixture asserting the generator's own output passes.** Still open; not part of
   this pass.

## Where the plan lives

The full interview design, the `verify` ladder detail, and the `release` publish path
are specified in the v1.0.0 plan of record, not repeated here to avoid a second copy
that can drift from the first.
