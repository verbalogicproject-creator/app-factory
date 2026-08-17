# Plugin roadmap — draft for near-future implementation

**Status: draft.** Nothing here is built. It exists to be argued with before code is
written, because the cheapest version of this work is the one that deletes a plugin
rather than implements it.

---

## The situation today

| Plugin | Files | Reality |
|---|---|---|
| `appfactory-core` | 216 | Real. One skill (`bootstrap`), guard hooks, the vendored runtime |
| `appfactory-plan` | 1 | `plugin.json` and nothing else |
| `appfactory-ui` | 1 | `plugin.json` and nothing else |
| `appfactory-build` | 1 | `plugin.json` and nothing else |

`marketplace.json` advertises detailed behaviour for all four. Install `appfactory-plan`
today and you get an empty manifest — but the listing promises an interview, a contract,
irreversible-decision ordering, and `UNVERIFIED.md`. That is the most damaging kind of
documentation error in this repository, because unlike a stale check count it is
discovered by a user, at first contact, on a promise.

---

## Decision 1 — stop advertising what does not exist

**Do this before any implementation work.** It costs minutes and it is not conditional on
the rest of this document.

Options, in order of preference:

1. **Remove the three entries from `marketplace.json`.** Re-add each when it is real. The
   listing then describes the product rather than the intention.
2. Keep them listed but prefix each description with `PLANNED — not yet implemented.`
   Weaker: a listing is a shop window, and a shelf labelled "coming soon" still occupies
   the shelf.

Option 1 is recommended. Nothing depends on the entries; `appfactory-core` is standalone.

---

## Decision 2 — is a four-plugin split right at all?

Worth asking before building three plugins. The honest case against:

- All three "Require appfactory-core". Three packages that cannot function without a
  fourth is not modularity, it is a dependency chain with no independent value.
- `appfactory-core` already vendors the entire runtime — the checks, the fixtures, the
  workflow templates, the scaffold. `appfactory-build` would own *a skill describing how
  to drive what core already ships*, not any capability of its own.
- `bootstrap` currently lives in core and already spans what `-plan` and `-build` claim.
- Every split multiplies the version-compatibility surface. This repository has already
  been bitten twice by a dependency that stopped being transitive.

The case for:

- The plugin is Claude Code's unit of installation, and a user who wants only the
  verification ladder should not be handed a UI-prototyping workflow.
- The four workflows genuinely differ in *when* they are used: once at project birth,
  repeatedly during design, continuously during build.

**Recommendation: three plugins, not four.** Collapse `-build` into `appfactory-core`,
because core already owns everything `-build` would describe and the split buys nothing
but a manifest. Keep `-plan` and `-ui` as real, separate plugins, because each owns a
distinct workflow with substantial content of its own.

If that is accepted, `appfactory-build`'s manifest should be deleted rather than
implemented — the highest-value outcome available here.

---

## Ordering, if the recommendation is accepted

Priority follows evidence: build first what today's failures proved is missing.

### 1. Fold `-build` into `appfactory-core` — smallest, do first

Add one skill, `verify`, to `appfactory-core`. It owns the workflow the last two days
established and which currently exists only as knowledge:

- run preflight, read its output, fix rather than suppress
- the rung ladder and what each rung can and cannot prove
- **artifact verification** — `scripts/verify-apk.sh`, and why "the build step exited 0"
  is not "the artifact is installable"
- physical-device instrumentation over wireless-debugging `adb`, including the five
  lessons in `docs/LOCAL-BUILDS.md` that each cost real time
- release closure: what evidence a tag requires, and what local evidence cannot prove

**Acceptance:** a fresh agent, given only this skill, reaches a verified signed APK
without re-deriving the aapt2 constraint, the install-both-APKs rule, or the animation
scales.

**Then delete `plugins/appfactory-build/`.**

### 2. `appfactory-plan` — the interview

Owns what `bootstrap` currently under-serves: the *decisions*, separately from the
*scaffold*.

- irreversible-decision ordering — `applicationId`, signing certificate, persisted schema
  version — asked first, with the consequence of each stated at the point of asking
- the compatibility lattice as a coupled set: AGP, Gradle, Kotlin, KSP, Compose BOM, Hilt,
  Room, Java target. Localmind's `libs.versions.toml` is the worked example, including
  why nothing is a range and nothing is a pre-release
- `targetSdk` taken from check `140`'s dated table rather than a literal
- `.appfactory/contract/UNVERIFIED.md` for anything guessed, flagged until confirmed

**Open question, needs a decision before work starts:** does `bootstrap` move out of
`appfactory-core` into `-plan`? Cleaner conceptually; breaks every existing install.
Recommendation: leave `bootstrap` where it is, have `-plan` *precede* it, and let
`bootstrap` consume the contract `-plan` produces.

**Acceptance:** a project generated after the interview passes all 20 checks on its first
preflight run — the generator's output is itself a fixture.

### 3. `appfactory-ui` — design contract to Compose

The largest and least specified. Content is genuinely available: Localmind's evidence-heavy
surfaces are a worked example of loading, empty, error, **refusal** and abstention states
as first-class, of citation placement, truthful truncation labels, and copy-with-provenance.

- publish every screen plus the navigation graph as one reviewable page before any Kotlin
  exists
- never emit a downloadable-font provider — a fabricated font certificate killed an app at
  launch through eleven green builds
- accessibility as a gate, not a pass: semantics, focus order, font scaling, minimum touch
  targets, and **assert in reading order** (a suite that scrolled backwards up a long
  container failed on one API level only)
- explicit submission over request-per-keystroke

**Dependency:** there is an existing `stitch-ui-resurrector` skill in this environment that
already converts design-tool output into idiomatic Compose. **Check whether `-ui` should
wrap it rather than duplicate it** before writing anything.

---

## Cross-cutting work, independent of the plugin split

These stand on their own and are cheap:

1. **A check that docs match the corpus.** "12 checks" survived in six places against 19 on
   disk. `manifest.sha256` drifted 86 files and 7 checks out of date with nothing verifying
   it. Both are the same disease: an assertion nobody checks. appfactory has **no CI of its
   own** — adding one that runs `selftest.sh`, verifies the manifest, and greps the docs for
   a stale count would close all three.
2. **Verify `manifest.sha256`, or delete it.** Nothing reads it today; `scaffold.py` walks
   the runtime tree directly. An unverified digest manifest is worse than none, because it
   looks like tamper-evidence.
3. **A fixture asserting the generator's own output passes.** The `targetSdk 34` case would
   have been impossible.

---

## What this roadmap deliberately does not promise

- No date. Both repositories are three days old and the failure rate has not stabilised.
- No claim that a split improves anything measurable. The strongest recommendation here is
  to build **one fewer** plugin than currently advertised.
- Nothing about Play publication, staged rollout, or store listings. That is release
  authority, and it stays with a human.
