# Getting started

## Install

```
/plugin marketplace add verbalogicproject-creator/appfactory
/plugin install appfactory-core@appfactory
```

Then, in the directory where the app should live:

```
/appfactory-core:bootstrap
```

## What bootstrap actually does

It refuses to be a template copy. The order below is the design, and each step exists
because skipping it caused a specific, recoverable-only-with-difficulty failure.

### 1. Settle the decisions that cannot be walked back

Two decisions have **no migration path** once a user installs, and one is
migration-sensitive. All three are settled first; the distinction matters when
something goes wrong.

| Decision | Status | Why |
|---|---|---|
| `applicationId` | **immutable** | changing it makes a different app; the old install cannot upgrade |
| signing certificate | **immutable** | Android refuses an update signed by a different key |
| persisted schema | migration-sensitive | it *can* change — that is what migrations are for — but the data is already on someone's device, so a wrong migration destroys it |

`bootstrap` asks for these first and **refuses to advance while any is `TBD`**.
Everything downstream is cheap to change. These are not.

### 2. Generate, then verify locally

`scaffold.py` writes a buildable single-module Compose app — about 25 files — and
validates `applicationId` against the package-name regex and `minSdk >= 26` *before*
writing anything.

Then `scripts/preflight.sh` runs 20 checks in roughly two seconds. This matters because
a CI round trip is 2–5 minutes; the entire point of the corpus is that a category of
mistake never costs that.

### 3. Key into the vault, and back it up

A new release keystore is generated and stored **inside** the encrypted vault, so there
is one file to back up and no `.jks` sitting on disk between builds.

The backup step is **blocking and requires typed confirmation.** Losing a release key
means the installed cohort can never be updated — there is no recovery path, no support
ticket, no workaround. It is the only failure in this pipeline with no remedy at all.

### 4. Push secrets, and prove they arrived

`pass_manager.py sync` pushes credentials to GitHub Actions, then `canary` proves it.

The proof is not optional theatre. **GitHub never returns a secret value**, so
`gh secret list` tells you a *name* exists and nothing more. The canary pushes a nonce,
dispatches a 15-second workflow that prints its SHA-256 to the step summary, and
compares. That is the only honest end-to-end evidence that a secret arrived.

This is not hypothetical: setting a secret here once failed **five times in a row with
no error message**, because interactive `gh secret set` fails silently without a TTY.
Five apparent successes, zero secrets set.

### 5. Drive to a launched APK

A walking skeleton — an app that launches, is signed, installs, and displays its own
`versionName`, `versionCode` and git SHA — goes all the way through CI, release and
onto a device **before any feature code exists.**

This is the highest-value ordering decision in the whole pipeline. After it, every
failure is attributable to app code rather than to the pipeline, which halves the
diagnostic search space for the rest of the project's life.

### 6. Report what is proven

Not "done" — a list of claims with the evidence for each, and explicitly which rungs
were *not* run.

## What you get in the repo

```
.appfactory/
  release/cert.sha256          the pinned signing identity (public, safe to commit)
  preflight-ignore             suppressions, each requiring a written reason
  bin/                         vendored tools
scripts/
  preflight.sh                 the runner
  preflight/checks/            20 checks
  preflight/fixtures/          a reproduction of every bug the checks catch
  local-toolchain.sh           doctor: can this machine build locally, and if not why
.github/workflows/
  ci.yml                       preflight -> compile -> test -> R8
  release.yml                  tag -> signed APK + AAB + mapping.txt + SHA256SUMS
  emulator.yml                 instrumented tests + release launch smoke
  secret-doctor.yml            the canary
```

## Day-to-day

```
./scripts/preflight.sh .        # 2 seconds, before every push
git push                        # the hook runs preflight and blocks on failure
gh run list --commit $(git rev-parse HEAD)
```

If a local toolchain is set up — see [`LOCAL-BUILDS.md`](LOCAL-BUILDS.md), and
`local-toolchain.sh` to check whether one is — the inner loop tightens considerably:

```
bash scripts/local-toolchain.sh            # is a local build possible here?
./gradlew :app:compileDebugKotlin          # 13-21s   types, KSP, Hilt graph
./gradlew :app:testDebugUnitTest           # ~45s     logic
./gradlew :app:lint                        # ~75s     patterns that compile and fail later
./gradlew :app:assembleRelease             # ~2m20s   R8
```

**This does not replace the push.** CI is the only x86_64 build, the only one on a
machine that is not yours, and the only place the emulator, signing and the cert pin
run. What local rungs buy is that a missing import stops costing a round trip.

Always pass `--commit` with a **full** SHA. `gh run list --limit 1` races the push and
happily returns the *previous* commit's run — which once had a fix reported as verified
by a run that never compiled it. A short SHA is worse: it returns an empty list and
exits 0. A guard hook denies both.

## Cutting a release

```
git tag -a v0.1.0 -m "..." && git push origin v0.1.0
```

`release.yml` derives `versionCode` and `versionName` from the tag, signs, and
**verifies the published APK's certificate against `.appfactory/release/cert.sha256`
before publishing.** That check has been deliberately falsified — a wrong pin produced
a correct rejection and nothing was published — before it was trusted.

If signing credentials are absent, the release variant is left **unsigned on purpose.**
An earlier version fell back to the debug signing config so a fresh clone would still
produce something installable. That was a trap: CI has no signing secrets, so every
"release" it published was signed with the runner's auto-generated debug key — a
different key every run. Unsigned fails loudly at install. Silently-differently-signed
does not.

## When something breaks

| Symptom | First thing to check |
|---|---|
| CI red on compile | `gh run view <id> --log-failed`, read the **first** error only |
| green build, crashes at launch | Hilt wiring, or a fabricated resource — check 060 and 070 |
| release APK will not install over the previous one | signing key changed; compare against the cert pin |
| a check "passes" but the bug is there | write the fixture, run the *existing* preflight against it, and watch it pass — that is the proof the check is blind |
| `gh` fails with `/data/local/tmp: no such file or directory` | set `TMPDIR` to a real writable path |

The last row is a real Termux/PRoot failure: `gh` defaults its temp directory to
`/data/local/tmp`, which does not exist under PRoot, and the error names the path
rather than the cause.
