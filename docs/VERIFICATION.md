# The verification ladder

Nine consecutive green builds once shipped an app that crashed before rendering a
pixel. Everything here exists because "the build passed" answers a much smaller
question than it appears to.

## The rungs

| # | Rung | Cost | Answers |
|---|---|---|---|
| V0 | authoring hooks | ~0.2s | am I about to do a known-bad thing? |
| V1 | static preflight | ~2s | is anything referenced but absent? |
| V2a | **local typecheck** | 13–21s | does it compile? |
| V2b | **local unit tests** | ~45s | is the logic right? |
| V2c | **local lint** | ~75s | is it a known-bad pattern that still compiles? |
| V2d | **local R8 / release APK** | ~2m20s | does minification break it? |
| V3 | CI compile | 2–4 min | does it compile **on x86_64, on another machine**? |
| V4 | CI unit tests | +30s | (as V2b, independently) |
| V5 | CI R8 / minify | +90s | (as V2d, independently) |
| V6a | emulator: instrumented + release launch smoke | 6–12 min | **does it launch?** |
| V6b | emulator: upgrade over previous | +40s | did the signing key drift? |
| V7 | physical device | manual | does it work on real hardware? |
| V8 | crash retrieval + retrace | 1–2 min | why did it die, at which commit? |

**V1 through V5 only ever prove it compiles.** V6a is the first rung that answers
whether the thing runs, and it must install and launch the **release** build.

The V2 rungs are new; `docs/LOCAL-BUILDS.md` is the setup and the measurements. They do
not delete V3–V5, and the reason is written into the table: V3 asks a *different*
question. A local build on the author's hand-assembled aarch64 toolchain agreeing with
itself is not evidence that a clean x86_64 checkout compiles. Two of this project's
worst bugs — an undeclared dependency and a missing committed file — compiled locally
and failed only in CI.

## A rung you have not watched fail is not a rung

This is the central discipline, and it was learned by getting it wrong.

The emulator rung was asserted to catch R8 failures in three commit messages and a
README table before anyone tested it. It did not. `testBuildType` silently defaults to
`debug`, R8 never runs for debug, and so an instrumented test asserting anything about
minification passes whether or not minification is correct. The suite reported 5/5 with
the keep rules deleted.

So every rung gets a negative case, and **the negative case must itself prove the
injected fault was real**:

| Rung | Injected fault | Proof the fault manifested |
|---|---|---|
| preflight | the bug each check targets | check exits 1, naming file and line |
| vacuous-test guard | delete all test sources | step reports `0` and fails |
| cert pin | sign with a throwaway key | digest mismatch, printing both values |
| launch smoke | `throw` in `Application.onCreate` | `crash.txt` retrieved from the device |
| R8 | reflection on a renamed class | **`mapping.txt` shows the rename** |

### The invalid negative test

That last row is a correction, and it is the subtlest failure in this project's
history.

The first attempt to prove the emulator rung caught R8 problems deleted the
hand-written kotlinx.serialization keep rules. Nothing broke — because the library
**ships its own consumer rules**, so the deletion was a no-op. The test passed, and had
this been checked only empirically the sequence would have been: fix the rung, watch
the test pass, conclude the rung works. More wrong than before, with more confidence,
and a green run as evidence.

Reading `mapping.txt` settled it, and revealed something worse: **R8 had deleted a
`@Serializable` DTO from the shipped APK entirely.** `mapping.txt` is published on
every release and had never once been read.

**A negative test that cannot demonstrate its fault is itself unvalidated.**

### Two methods, two error classes

Empirical falsification and authoritative documentation catch *different* things, and
neither substitutes for the other:

| Method | What it caught here |
|---|---|
| red branch (empirical) | `testBuildType` silently defaulting to `debug` |
| official docs (authority) | keep rules incomplete — **and the test premise void** |

## Why the emulator rung is not on every push

6–12 minutes versus roughly 3 for `ci`. It triggers on tags and a weekly schedule, so
the inner loop stays fast. Matrix over `minSdk` and `targetSdk`, AVD caching, one retry
on red before it is believed.

## Two rungs that are documented gaps

Stating these plainly is the point; a documented gap is safer than a rung that reports
success it has not earned.

**`connectedReleaseAndroidTest` hangs.** Setting `testBuildType = "release"` — which is
the correct way to make instrumented tests meet R8 — causes `am instrument` to time out
with the app process started and the runner never reporting. Six hypotheses were
eliminated: build, signing parity, runner renaming, test-class renaming, install,
registration, annotation stripping. Remaining candidate is Hilt plus minification.

R8 is covered two other ways instead, and the coverage is stated honestly rather than
assumed:

- **structure** — a CI step asserts against the published `mapping.txt` that classes
  which must survive were not removed or renamed
- **behaviour** — the app exercises the serialization path during startup, so R8
  breaking it becomes a launch crash, which the release launch smoke catches with
  `crash.txt` naming the cause

Not covered: arbitrary behavioural testing of the release variant.

**~~V2, local typechecking, does not exist.~~ — CLOSED.** The diagnosis in this
paragraph was correct in every part, so it is kept rather than deleted:

> `aapt2` is the only genuinely native blocker; Kotlin, KSP, R8 and Compose are all
> JVM. If it worked it would move the missing-import class of error from a 3-minute
> round trip to seconds.

Both halves held. Swapping four native binaries for aarch64 builds — and pointing AGP
at one of them, which is the step that is easy to miss — gave local compile, unit
tests, lint and R8. The missing-import round trip went from 2–5 minutes to 13–21
seconds, which is what the paragraph predicted. See `docs/LOCAL-BUILDS.md`.

Worth recording as method: this gap sat open for the project's whole life while the
correct diagnosis was written down in it. Nobody had tested the claim that made it look
closed — *"build-tools are x86_64-only"* — which is true of Google's build and not of
every build. **A documented gap is safer than an assumed rung, and it is still only as
good as the last time someone tried to close it.**

The remaining local gaps are named in `docs/LOCAL-BUILDS.md`: no local emulator (needs
an x86_64 image and KVM), no local signing, and a toolchain that has been assembled
once on one device.

## The vacuous test

`testDebugUnitTest` passes when there are no test sources at all. It reported success
in every repo in this lineage while verifying nothing.

The guard parses `test-results/**/*.xml` and fails when the aggregate `tests` attribute
is 0. It runs only when the Gradle step itself succeeded — an earlier `if: always()`
version added cascade noise on top of real compile failures, which buries the actual
error.

## Crash retrieval

`CrashLog` installs from `Application.attachBaseContext`, **not** `onCreate` — Hilt
builds its dependency graph inside `super.onCreate()`, so a crash there happens before
an `onCreate`-installed handler exists.

`crash.txt` carries `versionName`, `versionCode` and `GIT_SHA` in its first three
lines, so a diagnosis can refuse to proceed against a stale APK.

`logcat` is not a mechanism here: Termux has no `READ_LOGS`, so it returns **silence,
not an error** — which reads exactly like "no crash happened."

If `crash.txt` is absent, that is itself the diagnosis: the app died before
`attachBaseContext`, which means install, manifest or resources — not app code.
