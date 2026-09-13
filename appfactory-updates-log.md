# appfactory updates log

A running list of upgrades and gaps found while *using* appfactory on a real project,
so the changes can be made in one pass instead of interrupting the work that found them.

Nothing here is applied yet. Each entry carries the evidence, so none of it has to be
re-derived at apply time.

**Status key** — `OPEN` found, not yet fixed · `PROPOSED` fix drafted, not applied ·
`APPLIED` landed, with the commit · `DROPPED` investigated and rejected, reason kept.

Found during: Localmind Amber seven-surface shell, Aug 2026, aarch64 device
(NX779J / Android 15) with the local toolchain.

**Running tally.** 15 entries — 1 applied (10), 1 closed (11), 13 open.

**One more, uncounted, found while applying 10:** `CHECKS.md` opened with *"Twelve static
checks"* over a table of twelve, and the corpus had **eighteen** — 130 through 180 were
undocumented. Fixed in passing (table completed, count corrected, 190 added), but worth
noting as a pattern: the corpus grew and its own documentation did not, which is the same
drift the weekly version-rot canary exists to catch in dependencies. Nothing checks that
`CHECKS.md` lists every check, and something could.

---

## 1. `JAVA_HOME` is required but nothing enforces it

**Status:** OPEN
**Where:** `docs/LOCAL-BUILDS.md:37-42`, `plugins/appfactory-core/runtime/scripts/local-toolchain.sh:50-66`

**What happened.** A local `:app:connectedDebugAndroidTest` failed at *configuration* time
with:

```
Toolchain installation '/usr/lib/jvm/java-25-openjdk-arm64'
does not provide the required capabilities: [JAVA_COMPILER]
```

The machine has JDK 25 as the default `java` (JRE-only — no `javac` under that prefix) and
a full JDK 17 beside it. Gradle auto-detected 25 and stopped.

**Why it matters.** The doc says to `export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-arm64`
and `local-toolchain.sh` prints that exact line as a `fix`, but neither is on the path a
build actually takes. Nothing fails informatively. The error a reader hits names the JDK
that is *wrong* and never mentions that the right one is already installed two directories
away — which reads like "install a JDK" when the correct action is "select the one you
have". I wrote both files and still lost a build to this, in a fresh shell, a day later.

**Proposed change.** A preflight check (next free id) that fails when a `javac`-less JDK is
the one Gradle would resolve, naming a sibling JDK 17 if one exists. Fixture-first per
`docs/CHECKS.md`: `bug/` = a tree where the default JDK has no `javac`, and the existing
preflight must PASS against it before the check is written.

**Open question.** A check keyed on the *machine* rather than the *repo* is a new shape for
this corpus — every existing check reads files in the tree. That may argue for putting it in
`local-toolchain.sh` as a hard failure instead, and leaving preflight repo-only. Decide
before writing, not after.

---

## 2. A branch push gets no x86_64 validation, but the docs imply it does

**Status:** OPEN
**Where:** `docs/GETTING-STARTED.md:120-123`, `docs/LOCAL-BUILDS.md`, `.github/workflows/ci.yml`

**What happened.** `feat/amber-seven-surface-shell` was pushed to Localmind. No CI ran.
`ci.yml` triggers on `push: branches: ["main"]`, `pull_request: branches: ["main"]`, and
`workflow_dispatch` — a feature-branch push matches none of them.

**Why it matters.** Both docs make the same load-bearing claim: local rungs are a fast inner
loop and **"CI is the only x86_64 build"** — the implication being that pushing gets you
that check. On a feature branch it does not. In this specific case it means
`navigation-compose 2.9.8` has been resolved and built *only* on aarch64, and nothing has
yet proven it resolves on an x86_64 runner. The gap is silent: the push succeeds, the local
rungs are green, and there is no red anything to notice.

**Proposed change.** Either state the trigger boundary plainly in `GETTING-STARTED.md`
("a branch push runs nothing; open the PR or `gh workflow run ci.yml --ref <branch>`"), or
widen the `ci.yml` push trigger to `branches: ["**"]`. Prefer the doc fix plus an explicit
`workflow_dispatch` line in the day-to-day block — widening the trigger spends runner
minutes on every work-in-progress push, which is how teams learn to ignore CI.

---

## 3. The verification ladder has no on-device rung

**Status:** OPEN
**Where:** `docs/VERIFICATION.md` (V2a–V2d local rungs), `.github/workflows/emulator.yml`

**What happened.** The ladder documents local rungs V2a–V2d (compile, unit, lint, R8) and
treats instrumented tests as CI-emulator-only. `emulator.yml` runs on tags and a weekly
schedule — so on an ordinary day, instrumented tests run *nowhere*, and a suite can
accumulate for weeks without executing. Localmind reached 93 `@Test` methods across 8 files
in exactly this state.

The Android device the toolchain already runs on can execute them directly over
wireless debugging, at no CI cost:

```
adb pair <ip>:<pairing-port> <code>     # port + code from Developer options
adb connect <ip>:<connect-port>
./gradlew :app:connectedDebugAndroidTest
```

**Why it matters.** This is the same argument the whole local-toolchain document already
makes — the aarch64 machine can do more than was assumed — applied to the one rung still
marked unreachable. It closes the largest routinely-unverified surface in an Android
project.

**Proposed change.** Add it as a local rung in `VERIFICATION.md` with its honest caveats:
one physical device, one ABI, one OS version, and vendor-ROM behaviour that an emulator
would not reproduce — so it *supplements* `emulator.yml` and does not replace it.

**Now unblocked.** First run: **83 tests in 5m 15s** against NX779J / Android 15, over
wireless debugging, no CI involved. That is slower than the local unit rung and far faster
than waiting for a tag. The rung is real and worth documenting.

**Document these caveats with it:** one device, one ABI, one OS version, vendor ROM
behaviour an emulator would not reproduce — and **it drives the physical screen.** Activities
launch and tear down for five minutes straight, which looks exactly like a stuck home
button to anyone holding the phone. Warn before starting, not after.

---

## 4. A dropped device truncates the run and the summary does not say so

**Status:** OPEN
**Where:** `docs/VERIFICATION.md`, wherever the on-device rung from entry 3 gets written

**What happened.** The device went offline partway through (battery was at 16%). Gradle
reported:

```
Tests on NX779J - 15 failed: There was 11 failure(s).
...
Test run failed to complete. Expected 93 tests, received 82
```

**Why it matters.** The headline is "11 failures". The fact that **10 tests never executed
at all** appears once, in a line sandwiched between a ddmlib stack trace and the Gradle
failure banner, phrased as a count mismatch rather than as missing coverage. The XML records
83 testcases and says nothing about the 10 absent ones — there is no evidence of their
absence in the artifact a reader would consult.

This is the same failure shape the corpus already treats as its worst case: not a red
result, but a *green-looking or plausible-looking* result that has quietly stopped covering
something. A truncated run reads as a completed run with some failures.

**Proposed change.** The rung documentation must say: check `received N` against `Expected
N` before reading any failure list, and treat a mismatch as "the run did not happen" rather
than "the run had failures". If the rung gets a wrapper script, it should exit non-zero with
that message on its own, ahead of the test failures.

**Also:** charge the device or keep it plugged in. A five-minute screen-on run at 16%
battery is how this happened.

---

## 5. "Never executed" is not the same as "passing", and suites do not advertise which they are

**Status:** OPEN
**Where:** `docs/VERIFICATION.md`

**What happened.** 93 instrumented tests accumulated across 8 files over the course of the
work and were reported as delivered. On their **first ever execution**, 11 failed. Two of
those were not app bugs but tests that could never have failed:

- one asserts a substring that appears in **static help text** always on screen, so it
  would have passed against a completely broken validator;
- one is named `no_destination_declares_an_external_deep_link` and its body checks that
  every route exists in the graph — it does not look at deep links at all, so it would pass
  with a `navDeepLink` on every destination.

A further five failed for the mirror-image reason — they could never have *passed*. Four
asserted `onNodeWithText("…")` against a label the app exposes as a `contentDescription`,
which that matcher does not read; one asserted a value the UI deliberately stops rendering
in the configuration under test. Same root cause as the vacuous pair: never executed, so
never observed doing anything.

**Why it matters.** Both are the "nearly right" class that `docs/CHECKS.md` already treats
as more dangerous than an obviously-broken check — and `CHECKS.md` has a hard rule that
catches exactly this for preflight checks: *write the fixture, run the existing check
against it, and it must PASS before you write the check.* Instrumented tests get no such
discipline, and these two are what that gap produces.

**A third vacuous case, and the most instructive.** A test asserting that a label does not
wrap measured `onNodeWithText(...).getUnclippedBoundsInRoot()` — which resolves against the
**merged** semantics tree and so returned an *ancestor*, measuring the whole container. It
reported 91.3dp against a `Text` carrying `maxLines = 1`, which cannot wrap at all. The
number was real and described a different node, so the test could neither confirm the bug
nor confirm the fix — and it was the one assertion I trusted most, because it had a real
device observation behind it. Fix: `useUnmergedTree = true`.

This is the same failure a web geometry harness hit — identity on a non-interactive wrapper
reporting 41px for a 22px hit box — and it generalises: **a geometry assertion is only as
honest as the node it names.** Worth stating wherever the corpus discusses layout gates.

**Proposed change.** State in `VERIFICATION.md` that an unexecuted test is not evidence and
should be reported as pending, never as coverage. Consider whether the fixture-first rule in
`CHECKS.md` generalises to a stated expectation for tests: a new test should be observed
failing against the unfixed code once, before it is trusted.

---

## 6. The emulator rung is x86_64-only, so a whole class of defect is invisible to it

**Status:** OPEN
**Where:** `docs/VERIFICATION.md`, `.github/workflows/emulator.yml`

**What happened.** A physical arm64 device failed on the first instrumented run with

```
dlopen failed: library "libomp.so" not found: needed by .../libggml-base.so
```

Eight arm64 libraries declared `NEEDED libomp.so`; the packaging step never copied it.
**Zero x86_64 libraries declare it** — upstream enables OpenMP for arm64 only — and
`emulator.yml` runs `arch: x86_64` exclusively.

**Why it matters.** The emulator rung did not *miss* this on a bad day; it is structurally
incapable of finding it, and would have stayed green forever. That is a stronger claim than
"more coverage is better", and it is the honest argument for the device rung in entry 3: for
ABI-specific packaging, the phone is not a convenience, it is the only instrument.

**Proposed change.** State the ABI blind spot next to the emulator rung, so a green emulator
run is not read as "the native packaging is fine". Anything ABI-conditional — jniLibs,
`NEEDED` entries, per-ABI build flags — needs the device or an arm64 runner.

---

## 7. A release tag that names an upstream pin does not identify the artifact

**Status:** OPEN
**Where:** any project vendoring prebuilt binaries against a pinned digest

**What happened.** Native archives are published at tag `native-<llama.cpp pin>` and verified
against a committed `SHA256SUMS.txt`. Re-running the packaging workflow **without moving the
pin** replaced both assets under the same tag. Both digests changed — including x86_64, which
gained nothing, because a zip embeds member mtimes and the build is not reproducible.

**Why it matters.** Two different artifacts can exist under one tag, and the digest is the
only thing that distinguishes them. A changed digest therefore means **"rebuilt"**, not
**"contents differ"** — and under pressure a moved digest on a security trust anchor reads as
tampering. Worth saying out loud in the file itself, which is where it was recorded.

**Proposed change.** Where a pin names an upstream commit, the artifact identity should
include the packaging revision too, or the trust-anchor file should carry the caveat inline.

---

## 8. Republishing a pinned artifact breaks every build until the new digest lands

**Status:** OPEN

**What happened.** Pushing the packaging fix auto-triggered the rebuild (the workflow triggers
on its own path). From the moment the release assets were replaced until the new digests were
committed, `fetchNativeLibs` refused every archive — correctly, fail-closed — so every build
in that window failed for a reason unrelated to its own changes.

An emulator run was in flight across that boundary. It started at 15:04:29 and the release
republished at 15:09:55, so it fetched the old archives and passed the fetch step **by five
minutes of luck**. Had it straddled the swap, it would have failed on a digest mismatch that
had nothing to do with the tests it was dispatched to verify.

**Proposed change.** Sequence it: publish, commit digests, *then* dispatch anything that
builds. Or note the window explicitly so a mismatch during it is diagnosed in seconds instead
of investigated as a supply-chain event.

---

## 9. `performClick` on an off-screen node does not throw

**Status:** OPEN
**Where:** wherever the corpus discusses instrumented-test authoring

**What happened.** Two tests clicked a button below the fold of a scrolling column.
`assertIsDisplayed` failed honestly. `performClick` **did not** — it dispatched at a
coordinate outside the viewport, nothing happened, and the test surfaced as:

```
java.lang.AssertionError: expected:<1> but was:<0>
```

**Why it matters.** That message points at the callback. The callback was fine; the click
never landed. A test author reading it goes looking for a wiring bug that does not exist —
the same "the error names the wrong thing" shape as the JDK-25 toolchain message in entry 1
and the `adb pair` message below. Prepend `performScrollTo()` for anything that can scroll.

---

## 10. The libomp class of defect is STATIC, and a two-second check finds it

**Status:** **APPLIED** 2026-08-16 — check `190-native-libs-resolve` + fixtures + evasion
variant, `verify-apk-native-linkage.sh`, `CHECKS.md` updated, both vendored into Localmind
and wired into its `ci.yml`. Selftest clean at 19 checks.
**Where:** `preflight/checks/190-native-libs-resolve.sh`, `scripts/verify-apk-native-linkage.sh`

**Three things the implementation taught that the proposal had wrong:**

1. **It had to be split in two.** Pointed at build output, the check reported eight
   convincing failures from `intermediates/merged_jni_libs/release/` — a tree left by an
   `assembleRelease` from *before* the fix. Gradle never prunes intermediates, so a scan
   reports the worst state that directory has ever held. Every finding was true of the
   stale artifact and false of the source: the "cries wolf" failure 050 was rewritten for.
   Preflight now reads only what the **repository** declares, where staleness is
   impossible; `verify-apk-native-linkage.sh` reads a **named** artifact, so the caller is
   explicit about which one.
2. **The check pruned its own fixtures.** Written as the unanchored
   `-path '*/scripts/preflight/*'`, the exclusion matched each fixture's own absolute path
   — fixtures live under that directory — so every tree scanned nothing and all three
   "passed", `bug/` included. The selftest caught it on the first run. An exclusion meaning
   "inside the project being scanned" must be anchored to the project being scanned.
3. **On Localmind the check is inert, and says so.** This project vendors no `.so`; they
   are downloaded during the build. 190 correctly reports *"no native libraries"* and
   protects nothing here — which is why the artifact verifier is wired into `ci.yml` after
   `assembleRelease`. A check that cannot see the bug that motivated it is not finished.

**Both halves falsified before being trusted,** and the second against real data — the
pre-fix release tree still on disk:

```
UNRESOLVED  arm64-v8a/libggml-base.so needs libomp.so      ... 8 total, exit 1
```

The fixed debug APK: `40 native libraries across 4 ABIs, every DT_NEEDED resolves`.

---

### Original proposal, kept for the record

**Where:** new preflight check, or a Gradle verification task after packaging

**What happened.** Entry 6 argued the physical device was the only instrument for this defect.
That is true of the *emulator*, and it was the wrong conclusion to stop at: the defect is
static. Every packaged `.so` declares its dependencies in `DT_NEEDED`, and the bug was simply
that one of them resolved to nothing. No runtime is required to see that.

Walk every `lib/<abi>/*.so` in the APK, read `NEEDED`, and require each entry to be either a
platform-provided library or present in the same ABI directory:

```
arm64-v8a: all NEEDED entries resolve
armeabi-v7a: all NEEDED entries resolve
x86: all NEEDED entries resolve
x86_64: all NEEDED entries resolve
```

**FALSIFIED BEFORE BEING TRUSTED,** per `CHECKS.md`. Removing `libomp.so` from the extracted
tree made it name all eight offenders — the same eight, by name, that failed on the device:

```
UNRESOLVED: libggml-base.so needs libomp.so
UNRESOLVED: libggml-cpu-android_armv8.0_1.so needs libomp.so
... (8 total)
verdict: CORRECTLY FAILS without libomp.so
```

**Why it matters.** This cost a device round trip, a CI republish and a trust-anchor update to
discover. It costs two seconds to detect, needs no device, no emulator, no network — and it
is ABI-complete, checking armeabi-v7a and x86 as well, which neither the emulator (x86_64) nor
the phone (arm64) covers. Exactly the demotion 090 got from the emulator rung.

**It does not replace the device.** It proves every dependency is PRESENT, not that the
library LOADS — a missing symbol inside a present library would still pass. The residual risk
is much smaller than the gap it closes.

**Proposed change.** Add it fixture-first (`bug/` = a jniLibs tree with an unresolved NEEDED,
which existing preflight must PASS against first). Needs `readelf`, so declare that
dependency; and it needs a built APK or a merged jniLibs dir, which is a new input shape for
this corpus — likely a post-assemble step rather than a preflight check. Decide before
writing.

---

## 11. There is no adb-free path to instrumented tests without shell or root — settled

**Status:** CLOSED — question answered, no change proposed
**Supersedes** the second operational note below, which was right for the wrong reason.

Chased properly because the device owner has no routine Wi-Fi, so wireless debugging means
travelling to a public hotspot. The chain, each step killing a plausible theory:

1. `cmd activity instrument` refuses: `must be invoked through 'am instrument'`.
2. `/system/bin/am` needs `app_process`, and **`app_process` appeared not to exist.** It does.
   `/system/bin` is traversable but NOT LISTABLE from the container, so every `ls` and glob
   returned empty while `stat /system/bin/app_process64` shows 51,776 bytes. An earlier note
   here recorded the wrong conclusion from that.
3. Invoked by absolute path, `app_process` runs fine and prints the activity-manager help.
4. `am instrument` then fails with `asks to run as user -2 ... requires
   INTERACT_ACROSS_USERS_FULL` — which is not about instrumentation at all. `am` defaults to
   `--user current`, and -2 is what that resolves to.
5. With `--user 0`, the real boundary appears:
   `not allowed because it's not started from SHELL`.

`startInstrumentation` requires uid 2000 or root. An app uid cannot run instrumented tests,
by design. **A USB-connected computer, or root, is the only alternative to wireless
debugging** — which is why entry 10 matters so much more than it first looked.

Note steps 2 and 4 both reported something other than the actual obstacle, the same shape as
entries 1 and 9. Three separate times today the error named the wrong thing.

---

## 12. Verify a reported UI bug against commit timestamps before fixing it

**Status:** OPEN
**Where:** wherever the corpus discusses acting on a bug report or screenshot

**What happened.** Three device screenshots were supplied with a brief naming a truncated
chat header as a defect to fix. The truncation was real in the image. It had also been
fixed four hours earlier:

```
fix landed   1d32f16  2026-08-16 10:01
screenshots           2026-08-16 06:17-06:18
```

Two paired tests already pinned that layout from both sides and were green on API 28 and 36.

**Why it matters.** This layout had already been broken **twice, in opposite directions** —
once by an unconstrained child, once by over-constraining the fix. A third edit aimed at a
stale image would have been the third break, and it would have looked like diligence. The
check costs one `git log -S` against the changed expression and the file mtime of the
report.

Screenshots and bug reports carry a timestamp; the fix carries one too. Comparing them is
cheaper than re-deriving whether the bug still exists, and much cheaper than re-breaking a
passing layout.

**Proposed change.** State it as a step: before editing in response to any bug report,
establish whether the reported state is current. `git log -S'<expression>' -- <file>`
against the report's timestamp answers it in seconds.

---

## 13. A comment can assert behaviour the adjacent line forbids

**Status:** OPEN
**Where:** wherever the corpus discusses review or the "nearly right" class

**What happened.** A navigation item shipped as:

```kotlin
// ...a dead-silent disabled control is nearly as bad, so the tap says why.
NavigationBarItem(
    enabled = expertsAvailable,          // false
    onClick = { navController.navigate(...) },
```

The comment states the design intent correctly, argues for it well, and sits directly above
the line that makes it impossible: a disabled `NavigationBarItem` absorbs the press, so the
tap said nothing. The `contentDescription` beneath it announced the reason to TalkBack, so
the code even *looked* thorough — while a sighted user got a grey label and no explanation.

**Why it matters.** This is the "nearly right" family `CHECKS.md` already treats as the
dangerous state, in a form the corpus does not cover: not a pattern that matches too
loosely, but **prose that documents an intention the implementation contradicts**. It reads
as evidence the case was handled, which ends the investigation — exactly like a check that
passes while its bug is present.

A reviewer skimming for "was the disabled case considered?" finds a paragraph saying yes.

**Proposed change.** No mechanical check is plausible here — this needs naming, not
automating. Worth a line in the review guidance: when a comment claims a behaviour, the
claim is a testable assertion, and the test is the cheap way to find out whether the code
agrees with its own documentation. In this instance one JVM test on an extracted function
would have caught it, and that is what replaced it.

---

## 14. A test that renders a different composition than production is not a test of production

**Status:** OPEN
**Where:** wherever the corpus discusses UI testing, next to entries 5 and 13

**What happened.** A Compose destination assembled itself inline in the navigation graph:
`Column(verticalScroll(...))` wrapping a screen whose populated branch is a `LazyColumn`.
Two vertical scroll owners with the lazy one inside is an infinite-height measure and a
hard crash. It reached a user's phone.

Every rung was green. JVM tests, lint, R8, preflight, and **108 instrumented tests on two
API levels** — because the tests rendered the SCREEN in isolation while the graph wrapped
it in something else. The composition under test was never the composition that shipped.

A second condition hid it: the crashing branch was **unreachable** until a live backend
existed. Only a non-empty response builds the lazy list, so the first successful pairing
on real hardware was the first time that code had ever run.

**Why it matters.** This is the third distinct case in one project of a check that was
*structurally incapable* of finding what it appeared to cover — after tests that could
never fail (entry 5) and an emulator rung blind to an ABI by construction (entry 6). The
common shape is worth naming: **green means "the thing that ran, passed", and the gap is
always in what did not run.**

**Proposed change.** State it as a rule for UI tests: assert against the composable the
ROUTER uses, not a reassembly of its parts. Extracting the destination into one named
composable shared by the graph and the test is the cheap structural fix — a wrapper added
in either place then shows up in the other. Worth pairing with the observation that a
branch reachable only with a live backend has never executed, whatever the test count says.

**Postscript, and the reason this entry is not smug.** The regression test written to
cover it then failed four of its own assertions — three because they used
`performScrollTo` on rows a lazy list had not composed yet, having just replaced a
non-lazy assumption with a lazy list; and one because it matched `"Install"` as a
substring against the status text `"Installed, inactive"`. Knowing a rule and encoding it
correctly on the first attempt are different things, which is the argument for the
structural fix over the disciplinary one.

---

**Operational notes from the pairing/instrumentation work, worth keeping:**

- `adb pair` returns `protocol fault (couldn't read status message): Success` for *every*
  failure mode. A closed pairing port, an open non-pairing port, and a genuinely broken
  build are indistinguishable from the message. I concluded from a closed-port control that
  Termux's adb could not pair at all; it could, and the real cause was a pairing port that
  had already expired. **A pairing port lives only while the dialog is on screen** — if this
  becomes a documented rung, say that, because the misleading error costs more time than the
  step itself.
- `cmd activity instrument` refuses with `must be invoked through 'am instrument'`, and
  `am instrument` needs `app_process`, which is absent under PRoot. There is no
  adb-free path to instrumented tests from inside the container. `pm` works (it shells to
  `cmd`), which makes the dead end look reachable right up until it isn't.

---

---

## 15. A Compose UI assertion that scrolls BACKWARDS passes on new APIs and fails on old ones

**Status:** OPEN

**Observed.** `ExpertDetailRetrievalTest` asserted a quotation, then its provenance, then
scrolled back UP to check a status line above both. 118/118 green on API 36; on API 29 the
last assertion failed with "is not displayed". The app was correct on both. What changed
between the passing and failing runs was a test FIXTURE growing from one short quotation to
a 240-line one — long enough that the backwards scroll had somewhere to go.

**Why it is worth an entry.** The failure names the assertion, not the cause, so it reads
as a rendering bug on old APIs. It is not: `performScrollTo` brings a node into view, and
scrolling backwards through a tall container can land it against the viewport edge with no
visible height to assert on. The API where it fails is incidental; the ORDER is the defect.

**Proposed change.** State it as a rule for scrolling (non-lazy) Compose surfaces: **assert
in reading order, top to bottom, so every scroll moves forward.** It costs nothing, it is
how a user encounters the screen, and it removes an entire class of API-dependent
flakiness. Pair it with the existing lazy-list rule from entry 14's postscript — those two
together cover most scroll-related test failures:

- lazy list → `performScrollToNode` on the LIST, never `performScrollTo` on the row
- scrolling column → `performScrollTo` is fine, but only ever forward

**The wider pattern, again.** Entries 5, 6, 13 and 14 all reduce to *green means "the thing
that ran, passed"*. This one is the variant where the thing DID run, on one rung, and the
other rung was the honest one. A matrix that tests two API levels is worth keeping for
exactly this reason — the divergence was real information, not noise to be suppressed by
pinning to the newer image.

