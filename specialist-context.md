# AppFactory & Localmind — implementation context for the Android Compose Product Specialist

## 1. Purpose, authority, and proof limit

This is a **documentation-only evidence input**. It records what two repositories currently
contain, so that a provider-neutral Android Compose specialist can retrieve grounded
constraints, patterns, and failure lessons during planning, implementation, review,
debugging, testing, and release work.

**What this document is not:**

- Not a `.kpack`, not a runtime qualification receipt, not a source-standing decision.
- Not permission to redistribute any private corpus. No source bodies are copied here;
  behaviour is paraphrased and anchored by `path:line`.
- Not a claim that the specialist is built, mounted, evaluated, or runtime-qualified.
- Not a release-readiness assessment of either repository.

**Proof limit.** Every factual claim below is traceable to a file in one of the two named
repositories, or to a build/test observation made on this device and labelled as such.
Nothing here establishes that a shipped artifact behaves as described, that CI records are
complete, or that the owner's summary of release state is correct where local evidence
disagrees. Where evidence conflicts, **both sides are preserved** rather than resolved.

---

## 2. Repository identities and freshness

Inspected **2026-08-17**. Both repositories were clean before and after; the only write
performed by this task is this document.

| | AppFactory | Localmind |
|---|---|---|
| Root | `/root/projects/appfactory` | `/root/projects/localmind` |
| Branch | `docs/local-aarch64-builds` | `feat/amber-seven-surface-shell` |
| HEAD | `6b6f4f49d541633e2dca3e16de41aa9403055df4` | `11ebc8a9e5bffd0a8672b324970b1837b311f82b` |
| Status before | clean, in sync with origin | clean, in sync with origin |

Both matched the freshness hints in the request exactly. Neither repository contains an
`AGENTS.md` or `CLAUDE.md`; repository-local agent instructions do not exist in either.

**Disclosure of observer position.** Localmind's current HEAD includes commits authored
earlier in the same working session as this document. The build and device observations in
§6 were made during that development work — they are first-hand and reproducible, but they
were **not** produced by running anything for this documentation task. No build, test, or
project script was executed to write this file.

**Authorized deviation.** The originating request prohibited contacting external services.
The repository owner subsequently authorized reading **GitHub Actions run history**, which
is a read-only API query. §2.2 is the result. No other external call was made and nothing
was published, triggered, or mutated.

### 2.1 Repository scale and velocity — `observed`

| | AppFactory | Localmind |
|---|---|---|
| Commits | 27 | 98 |
| First commit | 2026-08-15 | 2026-08-15 |
| Latest commit | — | 2026-08-17 |
| Tags | — | 10 (`v0.0.1` … `v0.0.10`) |
| Tracked files | — | 330 |
| Kotlin source files | — | 151 |
| Unit test files | — | 29 |
| Instrumented test files | — | 15 |

**Both repositories are three days old.** That single fact reframes much of what follows:
these are not mature codebases whose documentation drifted over years, they are fast-moving
ones where documentation and implementation diverged within days. It also means every
"lesson" here is recent and none has been re-validated over time — a specialist should
weight them as *strong recent evidence*, not as settled practice.

The test-to-source ratio (44 test files against 151 source files) is `observed`; whether it
constitutes adequate coverage is **not** assessed here.

### 2.2 Continuous-integration run history — `observed`

130 runs, 2026-08-15 → 2026-08-17, read from the Actions API.

| Workflow | Success | Failure | Cancelled | Total | Pass rate | Median duration |
|---|---|---|---|---|---|---|
| `ci` | 50 | 13 | 3 | 66 | **76%** | 4.6 min |
| `emulator` | 26 | 16 | 0 | 42 | **62%** | 6.7 min |
| `native` | 4 | 2 | 5 | 11 | **36%** | 5.5 min |
| `release` | 10 | 0 | 0 | 10 | **100%** | 4.8 min |
| `secret-doctor` | 1 | 0 | 0 | 1 | 100% | 0.1 min |

Triggers: 84 `push`, 45 `workflow_dispatch`, 1 `schedule`.

**Four readings, and the third is the important one.**

1. **The cost ordering is real and measured.** `ci` at 4.6 min median versus `emulator` at
   6.7 min confirms the ladder's premise with independent data, and matches
   `docs/LOCAL-BUILDS.md`'s "2–5 min CI round trip" claim. It also confirms the value of
   local builds: the same document measures `assembleDebug` at ~1 min and
   `compileDebugKotlin` at 13–21 s locally.
2. **The expensive rung earns its place.** `emulator` fails at 38% against `ci`'s 24%. A
   more expensive rung that failed *less* often would be redundant; one that fails *more*
   often is catching a class of defect the cheaper rungs structurally cannot. This is the
   strongest available empirical support for pattern §5.1.
3. **`release` is 10 for 10, and that is exactly the trap.** A 100% pass rate on the release
   workflow coexists with §6.1, where the locally built release APK was uninstallable. The
   workflow proves it *builds*; it does not prove the artifact is valid. **A green release
   rung is not release evidence.** See §7 row 4.
4. **`native` is the least reliable rung** — 36% success with 5 cancellations, the only
   workflow with a significant cancellation count. `inferred`: this is consistent with
   long-running cross-ABI native builds being interrupted rather than with a systematic
   defect, but the cause is **not** established here.

Daily outcomes, `observed`:

| Date | Success | Failure | Cancelled | Success rate |
|---|---|---|---|---|
| 2026-08-15 | 58 | 21 | 8 | 67% |
| 2026-08-16 | 23 | 6 | 0 | 79% |
| 2026-08-17 | 10 | 4 | 0 | 71% |

`inferred`, weakly: the failure rate improved after the first day but has not stabilised,
and the sample is three days. **Do not read a trend into this.** It is recorded so that a
future comparison has a baseline, not as evidence that the corpus is reducing failures.

---

## 3. Evidence classification

Labels used throughout:

| Label | Meaning |
|---|---|
| `observed` | Read directly from current tracked source, or measured on this device |
| `documented` | A repository document asserts it; not independently re-verified here |
| `inferred` | A conclusion drawn from observed facts, marked where it is not certain |
| `recommended` | A proposal from this document; carries no repository authority |
| `unknown` | Could not be established from local evidence |
| `stale` | A repository statement contradicted by current observed state |

**Rule applied:** every material recommendation in §7 and §9–§11 is labelled
`recommended` and is not presented as repository fact.

---

## 4. Current Android stack and compatibility matrix

### Localmind actual — `observed`

| Component | Value | Anchor |
|---|---|---|
| AGP | 9.0.0 | `gradle/libs.versions.toml` `[versions] agp` |
| Gradle | 9.4.0 | wrapper |
| Kotlin | 2.3.0 | `libs.versions.toml` `kotlin` |
| KSP | 2.3.4 | `libs.versions.toml` `ksp` |
| Compose BOM | 2025.09.01 | `libs.versions.toml` `composeBom` |
| Hilt | 2.59 | `libs.versions.toml` `hilt` |
| Room | 2.8.3 | `libs.versions.toml` `room` |
| androidx.sqlite (bundled) | 2.7.0 | `libs.versions.toml` `sqliteBundled` |
| Navigation Compose | 2.9.8 | `libs.versions.toml` `navigationCompose` |
| Ktor (client, CIO) | 2.3.11 | `libs.versions.toml` `ktor` |
| kotlinx.serialization | 1.8.0 | `libs.versions.toml` `serialization` |
| Java / JVM target | 17 | `app/build.gradle.kts:294`, `:378` |
| compileSdk / targetSdk / minSdk | 36 / 36 / 28 | `app/build.gradle.kts:179`, `:186`, `:185` |
| applicationId | `com.verbalogix.assistant` (`.debug` suffix on debug) | `app/build.gradle.kts:182`, `:259` |
| Native ABIs | `arm64-v8a`, `x86_64` | `app/build.gradle.kts:171` |
| Room schema versions | 1–4 committed | `app/schemas/*/{1..4}.json` |
| Release shrinking | `isMinifyEnabled = true` | `app/build.gradle.kts:263` |

### Upgrade-sensitive couplings — `observed`

- **AGP 9 removed `kotlinOptions`.** `jvmTarget` is set through the Kotlin DSL extension
  instead (`app/build.gradle.kts:373–378`). An AGP downgrade breaks this and vice versa.
- **AGP 9 provides Kotlin support itself**; applying `kotlin.android` separately is an
  error (`app/build.gradle.kts:14–16`). This is a real trap for anyone porting a
  pre-AGP-9 template.
- **Transitive dependencies are declared explicitly.** The catalog records two incidents
  where a symbol arrived only transitively and later vanished (`material-icons-core` via
  material3; `kotlinx-serialization-json` via Ktor). Preflight check `050` enforces that an
  import maps to a declared artifact.
- **No pre-release versions and no version ranges**, stated as policy in the catalog
  comment beside `navigationCompose`.
- **Bundled SQLite is a deliberate FTS5 decision**, not a default: the device's system
  SQLite frequently lacks FTS5, and an API 36 emulator failed with `no such module: fts5`.
  Uses the new driver API, not `SQLiteOpenHelper`.
- **Native library is pinned by commit + digest**, not tracked (`native/llama.cpp.pin`).
  Upstream has no stable channel; "latest" is not a version.

### AppFactory defaults vs Localmind actual — contradictions

| Topic | AppFactory says | Localmind does | Verdict |
|---|---|---|---|
| `targetSdk` | `34`, recommended by the bootstrap skill (`plugins/appfactory-core/skills/bootstrap/SKILL.md:34`) | `36` | **`stale` and self-contradictory — see §7** |
| `minSdk` | `28` (`SKILL.md:33`) | `28` | consistent |
| Local SDK availability | "from a phone with no Android SDK" (`README.md:4`) | full local aarch64 toolchain in use | `stale` framing — see §7 |
| Preflight check count | 12 (`README.md:99`, `:113`, `:130`; `docs/GETTING-STARTED.md:42`, `:92`) | 19 on disk, IDs `010`–`190` | **`stale`** |

---

## 5. Reusable implementation patterns

Each entry: what it is, when it applies, why it exists, anchor, proof limit.

### 5.1 Cost-ordered verification ladder

**Pattern.** Order verification rungs by cost, not by category, and optimise
**time-to-failure** rather than build speed. AppFactory's ladder is: static preflight (~2 s)
→ compile → unit → lint → R8 release build → x86_64 CI → API-level emulators → physical
device.

**Why.** `documented` at `README.md:19` — when a round trip costs minutes, the valuable
property is how early a mistake is caught.

**Measured support — `observed`, §2.2.** Across 130 runs the ordering holds: `ci` median
4.6 min at a 76% pass rate, `emulator` median 6.7 min at 62%. The dearer rung fails *more*
often, which is precisely what justifies paying for it.

**Proof limit.** The ordering is only sound if each rung actually answers a question the
cheaper ones cannot. §6.1 and §7 both record cases where a rung reported success without
answering its question — and §2.2 shows the sharpest instance: `release` is 10 for 10 while
the artifact it produced locally could not be installed.

### 5.2 Fixture-first checks — every check ships a failing case

**Pattern.** Each preflight check carries a `bug/` tree it must fail and a `fixed/` tree it
must pass. `observed`: 19 checks, each with a fixture directory under
`plugins/appfactory-core/runtime/scripts/preflight/fixtures/`.

**Why.** A check with no failing fixture is untested and may be vacuous. The `140` fixture
README records the strongest form of this: *"all 13 existing checks pass on this tree"* —
the corpus was demonstrably blind to a `targetSdk` that would have blocked Play submission.

**Generalises:** yes. This is the single most transferable practice in AppFactory.

### 5.3 Machine-specific config never enters the repo

**Pattern.** Absolute paths and credentials live in `~/.gradle/gradle.properties`,
`local.properties`, or CI secrets — never in tracked files.

**Anchor.** `docs/LOCAL-BUILDS.md:120–133`, stated with the reasoning: CI is x86_64 and the
path would neither exist nor be the right architecture; other contributors would inherit
someone's home directory.

**Related, `observed` in Localmind.** Release signing reads from a git-ignored
`keystore.properties` or from environment variables, and **falls back to unsigned rather
than to the debug key** (`app/build.gradle.kts:23–46`). The comment records why: an earlier
version fell back to debug signing, so every CI "release" was signed with the runner's
auto-generated key — a *different* key each run, silently not upgrade-compatible. Unsigned
fails loudly; wrongly-signed does not.

### 5.4 Immutable decisions are asked first

**Pattern.** `applicationId`, signing certificate, and persisted schema version cannot be
changed after first install. AppFactory's planning stage is described as asking these first
and writing guesses to `UNVERIFIED.md`.

**Proof limit — important.** This behaviour is `documented` in
`.claude-plugin/marketplace.json` only. The plugin that would implement it is a stub
(§7). Treat the *principle* as reusable and the *implementation* as absent.

### 5.5 Strict-by-configuration contract decoding

**Pattern.** For a contract that declares `additionalProperties: false`, configure the JSON
decoder strictly and let it refuse, rather than relying on convention.

**Anchor.** `app/src/main/java/com/verbalogix/assistant/data/harness/HarnessDecoder.kt:32–38`
— `ignoreUnknownKeys = false`, `isLenient = false`.

**Why it generalises.** A lenient decoder silently accepts a payload that violates the
contract, and the divergence surfaces later as a digest mismatch with no indication of which
byte moved.

### 5.6 Make invalid states unrepresentable rather than detectable

**Pattern.** Where a model or external system could emit an identifier, give it an **index**
instead and resolve the identifier client-side.

**Anchor.** `data/harness/GroundedAnswerParser.kt` — the model is shown a numbered evidence
list and writes `[1]`; it never handles an evidence id. A hallucinated 64-hex id would have
to be rejected by lookup; a hallucinated `[9]` against three items is out of range by
construction.

**Generalises:** yes, well beyond Android — this is a general contract-design lesson.

### 5.7 Ticket ordering, not cancellation, for stale async results

**Pattern.** To stop an overtaken response from replacing a newer one, compare a
monotonically increasing ticket at the point of publication. Do **not** rely on coroutine
cancellation.

**Anchor.** `ui/evidence/RetrievalController.kt` — the reasoning is recorded there:
cancelling does not recall bytes already on the wire, and a coroutine past its last
suspension point runs to completion anyway, which is exactly the window where an overtaken
response would publish.

**Generalises:** yes. Applies to any search-as-you-submit UI.

### 5.8 Comment-as-correction, and comments that claim less than the code

**Pattern.** When a comment's claim stops being true, correct it explicitly rather than
deleting it. `observed` in `RetrievalController.kt`, where a paragraph records that it
previously claimed the question was never held at all, and why that was withdrawn.

**Why.** A comment claiming a stronger property than the code provides is worse than no
comment, because a reviewer checks the comment instead of the code.

### 5.9 Tripwire tests for identities that must move together

**Pattern.** When two values must change in the same commit — an id and the digest of what
it names — pin both in a test whose failure message says what to do.

**Anchor.** `app/src/test/java/com/verbalogix/assistant/data/harness/GroundedTurnPromptTest.kt`
pins `TEMPLATE_ID` and `TEMPLATE_SHA256` together. Localmind bumped
`localmind/grounded-turn/1.0` → `1.1` when the prompt text changed, because receipts record
the pair and two different templates behind one name make the pair meaningless.

**Anti-pattern to warn about:** "fixing" such a test by updating only the digest.

### 5.10 Golden-byte encoder tests, not field-equality tests

**Pattern.** For a payload whose digest is checked by a server, assert **byte equality**
against a golden, feeding the builder inputs read *out of the golden itself*.

**Anchor.** `app/src/test/java/com/verbalogix/assistant/data/harness/AssistantTurnGoldenTest.kt`.
The rationale recorded there: a wrong decoder refuses a valid document and says so; a wrong
**encoder** produces a request the server hashes differently, and the only symptom is an
opaque `request-invalid`.

---

## 6. Failure-derived lessons

Format: symptom → root cause → detection rung → fix → prevention → generalises?

### 6.1 A "Proven" release build that could not be installed

- **Symptom.** `INSTALL_PARSE_FAILED_UNEXPECTED_EXCEPTION: Failed to parse … AndroidManifest.xml`.
  `aapt2 dump badging` reported *could not identify format of APK*; `apksigner` reported
  *Missing AndroidManifest.xml*. The zip itself was intact (`unzip -t` clean).
- **Root cause.** `observed`. With **aapt2 2.19-20250916.230514** as
  `android.aapt2FromMavenOverride`, the release path (`isMinifyEnabled` +
  `isShrinkResources`) packaged an APK containing dex, native libraries and assets but **no
  `AndroidManifest.xml` and no `resources.arsc`**. AGP's own shrunk resource archive
  (`app/build/intermediates/shrunk_resources_binary_format/release/**/*.ap_`) was **correct**;
  only the final merge lost them. Debug and androidTest APKs were unaffected.
- **Fix.** aapt2 **2.20-android-16.0.0_r4** (Termux `pkg install aapt2`) packages it
  correctly — verified: manifest and `resources.arsc` present, parses, signs, installs.
- **Detection rung.** None. It passed every rung AppFactory documents. It was found only by
  attempting an install on a physical device.
- **Prevention (`recommended`).** After any release build, assert that the APK contains
  `AndroidManifest.xml` and `resources.arsc`. This is a two-line zip check and belongs in
  the preflight corpus or the release workflow.
- **Generalises:** yes, to any non-x86_64 local Android toolchain.
- **Direct bearing on AppFactory.** `docs/LOCAL-BUILDS.md:81` recommends the 2.19 binary by
  name, and `docs/LOCAL-BUILDS.md` lists `assembleRelease` under **"Proven"** — *"R8 runs,
  produces a 23 MB unsigned APK and a 35 MB mapping.txt"*. Both halves of that observation
  are true and neither implies the APK was **valid**. The check performed was "R8 ran and a
  file exists", not "the artifact is installable". This is the same failure mode the same
  document warns about elsewhere.
- **Corollary, `stale`.** Any earlier local claim of release-build health made on this
  device before the aapt2 upgrade should be discounted. One such claim — *"assembles
  cleanly, 40 native libs across 4 ABIs, every `DT_NEEDED` resolves"* — inspected only
  native libraries and was made against an APK missing its resources.

### 6.2 "Instrumentation hangs on the release variant" was a crash

- **Symptom.** `connectedReleaseAndroidTest` produced no output, never printed
  `Starting N tests`, and ran to the 45-minute job timeout. Recorded in
  `localmind/app/build.gradle.kts:209–226` as evidence that behavioural testing of the
  minified variant is unachievable.
- **Root cause.** `observed`, from `adb shell dumpsys dropbox --print`:
  `java.lang.NoClassDefFoundError: Failed resolution of: Landroidx/tracing/Trace;` at
  `androidx.test.runner.AndroidJUnitRunner.onCreate`. `AndroidJUnitRunner` executes **inside
  the app's process** and resolves against the **app's** classes. R8 correctly removed
  `androidx.tracing.Trace` because the app never calls it; the runner does, in `onCreate`,
  before reporting anything. The process dies before the first status line, which upstream
  is indistinguishable from a hang.
- **Second-order cause.** Two instrumented tests referenced a fixture in `src/debug`, which
  the release variant does not compile — so the release suite failed in the Kotlin compiler
  before ever reaching a device. **A test that reads another variant's source set pins the
  entire suite to one build type.**
- **Fix.** Fixture relocated into `androidTest`; keep rules confined to
  `app/proguard-instrument-release.pro` behind an opt-in `-PinstrumentRelease` flag, so
  shipped minification is unchanged.
- **Fidelity cost, stated.** The keep list did not stay small: after `androidx.tracing.Trace`
  came `kotlin.LazyKt`, because the test APK carries no Kotlin runtime of its own. The rules
  now keep `kotlin.**` and `kotlinx.coroutines.**`. **A green run under that flag means "R8
  did not break the app's own code", not "the shipped APK is verified."**
- **Status.** `unknown` — the suite has still never completed against the minified build;
  every attempt ended on a dropped adb link, never on a test result. `observed` separately:
  the minified app **launches** cold in 256 ms with `MainActivity` resumed, so R8 does not
  break the application itself.
- **Generalises:** yes. Any project considering `testBuildType = "release"` will meet this.

### 6.3 Instrumented tests on a physical device without an emulator

- **Symptom / gap.** `docs/LOCAL-BUILDS.md` lists instrumented tests under **"Not proven"**,
  reasoning that an x86_64 system image and KVM are unavailable, so the rung stays CI-only.
- **Observed reality.** The full suite ran on the physical aarch64 device — **132 tests,
  0 failures** — via wireless-debugging `adb` from inside PRoot. The emulator is not the only
  way to reach that rung.
- **Mechanics that made it work (all `observed`):**
  - Wireless debugging needs a **Wi-Fi interface**, not a Wi-Fi *network*; the phone's own
    hotspot suffices. `adb pair` is one-time and persists in `~/.android/adbkey`; only the
    **connect port** rotates.
  - `adb mdns services` returns nothing from PRoot (no multicast), so the port must be read
    from the Wireless-debugging screen.
  - The SDK's `adb` has Openscreen mDNS; Termux's build does not.
  - **Do not run `connectedAndroidTest` over a flaky link.** Gradle compiles for minutes
    before looking for a device. Pre-build, then `adb install` + `adb shell am instrument`
    (~1 minute).
  - **Always install both APKs.** Skipping the install produced **68 `NoSuchMethodError`**
    from a stale app/test APK mismatch that reads exactly like real test failures.
  - Zero `window_animation_scale`, `transition_animation_scale`, `animator_duration_scale`
    before running — emulators default to 0, phones do not — and restore afterwards.
  - This ROM filters logcat; app lines never appear. Crashes come from
    `adb shell dumpsys dropbox --print`.
- **Generalises:** partially. The adb technique is general; the logcat filtering is
  OEM-specific.

### 6.4 A comment that failed a static check

- **Symptom.** `FAIL the build references 'instrumentRelease' but no such file exists`.
- **Root cause.** `observed` at
  `plugins/appfactory-core/runtime/scripts/preflight/checks/020-build-referenced-files.sh:35–40`.
  The check slurps the whole build file and matches `\w*[Pp]roguardFiles?\s*\((.*?)\)\s*$`
  with `/gms`, harvesting every quoted string in the capture. Writing that function's name
  **followed by an opening paren inside a comment** opened a match that ran to the next
  line-ending paren and swallowed a `hasProperty("…")` literal as a filename.
- **Fix.** Name the function without parentheses in prose; read the property into a `val`
  well away from any rules-file argument list.
- **Prevention.** The check is not wrong — it cannot know which literals are paths. Adding an
  exception would weaken it. `recommended`: document the constraint rather than relax the
  check. Note the check's own header already records two prior near-misses in its history,
  both of which let a bug through while reporting success.
- **Generalises:** yes, as a caution about regex-over-source checks: they read comments too.

### 6.5 Carrying a stale green forward

- **Symptom.** An emulator run failed on an assertion for a fixture string.
- **Root cause.** A fixture was moved between source sets **and** its text changed in one
  commit; the assertion was left behind. The physical-device run cited as evidence predated
  the move and was never evidence about that change.
- **Prevention.** A passing run is evidence only about the tree it ran against. `recommended`:
  when changing a fixture's text, grep for the literal before assuming coverage.
- **Generalises:** yes.

### 6.6 Killed builds leave Gradle believing stale outputs are current

- **Symptom.** After interrupting a build, subsequent builds packaged an APK from a
  poisoned intermediate and reported success; deleting the output directory did not help,
  because Gradle's up-to-date check is not "does the file exist".
- **Prevention.** After an interrupted build, clean the affected variant rather than trusting
  incrementality. `inferred` — this compounded 6.1 and cost two diagnostic cycles.

### 6.7 Historical lessons recorded in-repo (`documented`, not re-verified here)

Preserved because they shaped the check corpus and remain instructive:

- A **fabricated downloadable-font certificate** killed an app at launch through eleven
  green builds (`.claude-plugin/marketplace.json`, appfactory-ui description).
- A missing `@HiltAndroidApp` registration and **R8 stripping a kotlinx.serialization
  serializer** each produced apps that compiled perfectly and died at launch
  (`localmind/.github/workflows/emulator.yml` header).
- `targetSdk 34` fell below Play's submission floor and **13 existing checks passed on the
  broken tree** (`fixtures/140-target-sdk-submittable/README.md:41`).
- Two symbols vanished when a transitive dependency stopped being transitive
  (`libs.versions.toml`, `navigationCompose` comment).

---

## 7. AppFactory missing/outdated matrix

**No corrections were made in the task that produced this document.** Severity is this
document's assessment.

> **Subsequent status, added after the fact.** The repository owner separately authorized
> acting on this matrix, and commit **`4e36ae5`** ("Gate the artifact, not the build step")
> addressed rows 1, 3, 4, 5, 9 and 10. The rows are **left as originally written** rather
> than rewritten, because the finding and the fix are different pieces of evidence and a
> matrix that silently reflects only the current state cannot show that the gap ever
> existed. The `Status` column below records what changed.
>
> | Row | Status after `4e36ae5` |
> |---|---|
> | 1 — check count | **fixed** — six occurrences updated 12 → 20 |
> | 2 — `targetSdk 34` | **open** — bootstrap still recommends a value check 140 rejects |
> | 3 — aapt2 guidance | **fixed** — `docs/LOCAL-BUILDS.md` now requires ≥ 2.20 and documents the silent 2.19 failure |
> | 4 — `assembleRelease` "Proven" | **fixed** — claim narrowed in place; `scripts/verify-apk.sh` now gates it in `ci.yml` and `release.yml` |
> | 5 — instrumented tests "Not proven" | **fixed** — moved to "Proven" with the physical-device adb procedure |
> | 6 — stub plugins | **open** — `-plan`, `-ui`, `-build` still manifest-only while advertised |
> | 7 — licence | **open** — Apache-2.0 declared in four manifests, no LICENSE file |
> | 8 — "no Android SDK" framing | **open** — headline unchanged |
> | 9 — APK validity check | **fixed** — `scripts/verify-apk.sh`, proven against a reconstructed bad artifact |
> | 10 — variant coupling | **fixed** — preflight check `200`, with `bug/`, `bug-fqn/` and `fixed/` fixtures |
>
> Also fixed but not originally listed: `runtime/manifest.sha256` was **86 files and 7
> checks out of date** and has been regenerated. That it drifted unnoticed, and that
> nothing in the repository verifies it, is itself an open finding.

| # | Topic | Current claim / omission | Observed reality | Severity | Recommended correction | Evidence |
|---|---|---|---|---|---|---|
| 1 | Preflight check count | "12 checks" in four places | **19** checks on disk, `010`–`190` | Medium | Derive the count at doc-build time, or add a check asserting docs match the corpus | `README.md:99,113,130`; `docs/GETTING-STARTED.md:42,92`; 19 files under `runtime/scripts/preflight/checks/` |
| 2 | `targetSdk` recommendation | Bootstrap recommends **`targetSdk 34`** | Check `140` exists **specifically to fail** `targetSdk 34`; Localmind uses 36 | **High** — the pipeline's own guidance fails its own gate | Recommend the current Play floor, and add a fixture asserting the bootstrap default passes check `140` | `plugins/appfactory-core/skills/bootstrap/SKILL.md:34` vs `fixtures/140-target-sdk-submittable/bug/app/build.gradle.kts:7` |
| 3 | aapt2 version guidance | Recommends the 2.19 build-tools-36 binary | 2.19 **silently strips `AndroidManifest.xml` and `resources.arsc`** from release APKs; 2.20 fixes it | **High** — documented path yields uninstallable release artifacts | Require aapt2 ≥ 2.20 for local release builds; add an APK-validity assertion | `docs/LOCAL-BUILDS.md:81`; §6.1 |
| 4 | `assembleRelease` listed as "Proven"; `release` workflow 10/10 green | "R8 runs, produces a 23 MB unsigned APK" | True and insufficient — that APK was unparseable and uninstallable, while the release workflow passed every time | **High** | Redefine the rung as "produces an APK that `aapt2 dump badging` can read", not "R8 ran" | `docs/LOCAL-BUILDS.md`, "Proven" list; §2.2; §6.1 |
| 5 | Instrumented tests "Not proven" locally | Blocked on x86_64 image + KVM, so CI-only | 132 instrumented tests ran **on the physical device** via wireless-debugging adb | Medium — an available rung is documented as unavailable | Add a physical-device instrumentation section with the adb mechanics in §6.3 | `docs/LOCAL-BUILDS.md`, "Not proven" list; §6.3 |
| 6 | Plugin completeness | `marketplace.json` advertises detailed behaviour for all four plugins | `appfactory-plan`, `-ui`, `-build` contain **exactly one file each** — `plugin.json`. Only `appfactory-core` (216 files) is implemented | **High** — installing an advertised plugin yields nothing | Mark the three as planned, or gate them out of the marketplace until implemented | `plugins/*/`; `.claude-plugin/marketplace.json` |
| 7 | Licence | Every `plugin.json` declares `"license": "Apache-2.0"` | **No `LICENSE` or `COPYING` file exists** at the repo root | **High** — declared terms are unenforceable and reuse expectations are undefined | Add the Apache-2.0 text, or correct the declarations | `plugins/*/.claude-plugin/plugin.json`; root listing |
| 8 | "No Android SDK" framing | Headline says "from a phone with no Android SDK" | A full local aarch64 toolchain is documented and in use; README already concedes the constraint "has since been lifted" | Low — internally acknowledged but the headline and marketplace description still lead with it | Reword the headline; keep the historical constraint as the design rationale it is | `README.md:4`, `:19`, `:25`; `.claude-plugin/marketplace.json:4` |
| 9 | Release-artifact validity check | No check asserts an APK is well-formed | Two independent failure modes (§6.1) produced structurally valid zips that no tool could read | Medium | Add check `200`: release APK contains `AndroidManifest.xml` + `resources.arsc` | absence across `runtime/scripts/preflight/checks/` |
| 10 | Variant-coupling in tests | No check detects it | An `androidTest` reference into `src/debug` silently pins the suite to one build type | Medium | Add a check flagging `src/debug`/`src/release` package references from `androidTest` | §6.2 |

---

## 8. Localmind specialist profile

Constraints that should **tailor** retrieved Android guidance for this project without
leaking into general advice.

- **Read-only authority boundary.** The app reads a declared surface and writes nothing.
  Scopes are exactly `capabilities:read`, `expert:read`, `query:read`, `token:refresh`.
  General Android advice about file creation, background sync, or tool execution is
  **inapplicable** here and should be withheld rather than adapted.
- **Nothing sensitive is persisted.** Pairing credential and access token are memory-only
  and never written to Room, `SavedStateHandle`, logs, crash records, or analytics. Query
  text is held only while the evidence it produced is on screen. Standard "cache the token"
  guidance is an anti-pattern in this project.
- **One inference provider, off-device.** The app is an HTTP client to llama-swap on
  `127.0.0.1:8090`. It does not choose backends or offload. The in-process engine is
  CPU-only because the vendored binding exposes only `loadModel(path)` and
  `sendUserPrompt(text)` — there is no offload setting to expose, so advice about
  configuring one is inapplicable.
- **Contract changes are atomic.** A schema is admitted only together with its strict
  decoder, exact golden-byte test, request builder, and UI disposition handling, in one
  change. Checked-in schemas and goldens are authoritative and must not be transcribed or
  reinterpreted.
- **Evidence-only presentation.** No generated score, confidence, narration, or invented
  labels. `succeeded`, `abstained`, `conflicted`, `refused`, expired-session, and
  schema-mismatch each get distinct wording. The word "grounded" appears on exactly one code
  path, and that path has a server-closed receipt behind it.
- **Frozen scope for v0.1.0.** No AesCoder, Builder Canvas, sandbox, file creation, new
  provider, model configuration, tool authority, or navigation additions.
- **Environment.** Development happens on the target device class itself (aarch64, PRoot,
  Termux). Advice assuming an x86_64 workstation, a connected emulator, or `adb` over USB is
  frequently wrong here.

---

## 9. Proposed knowledge-module split — `recommended`

The UX pack must **depend on** a qualified Foundations pack rather than duplicate it.

### `kf:pack:android-compose-foundations`

Build and correctness substrate: AGP/Gradle/Kotlin/KSP compatibility and AGP-9 migration
traps; version-catalog discipline (explicit transitives, no ranges, no pre-releases);
immutable decisions (applicationId, signing identity, schema version, min/target/compile
SDK, ABI set); Room/bundled-SQLite schema ownership and migration evidence; Hilt wiring;
Ktor loopback clients and strict-versus-lenient decoding; R8 and keep-rule reasoning
including the instrumentation fidelity cost; native packaging, ABI coverage, digest
pinning; the verification ladder and fixture-first checks; Termux/PRoot/aarch64 toolchain
including the aapt2 version constraint; physical-device instrumentation mechanics; signing
custody and release-artifact identity.

### `kf:pack:android-product-ux-patterns`

Product surface: Compose state modelling and state ownership; loading, empty, error,
**refusal**, and abstention states as first-class; evidence-heavy interfaces (citation
placement, progressive disclosure, truthful truncation labels, copy-with-provenance);
accessibility — semantics, focus order, font scaling, minimum touch targets, reading-order
assertions; responsive layout and safe areas; explicit submission versus
request-per-keystroke; naming and labelling honesty (never label a retrieval an answer);
stale-result suppression as a UI correctness property.

### Shared, and where they belong

| Topic | Home | Note |
|---|---|---|
| Stale-result / ticket ordering | Foundations | UX pack cites it; concurrency is substrate |
| Process death & `SavedStateHandle` | Foundations | UX pack adds "what must not be saved" |
| Test-fixture hygiene, variant coupling | Foundations | |
| Compose test mechanics (animation scales, merged semantics) | Foundations | UX pack cites for accessibility assertions |
| Copyable receipts / provenance affordances | UX | Depends on Foundations' digest concepts |

---

## 10. Candidate evaluation set — `recommended`

Positive cases:

1. *"We're starting an Android app. What must we decide before the first commit?"* →
   applicationId, signing certificate, persisted schema version, min/target/compile SDK,
   ABI set. Must state these are irreversible after first install.
2. *"Our release APK won't install: `INSTALL_PARSE_FAILED_UNEXPECTED_EXCEPTION`, manifest
   named."* → must ask for the aapt2 version before suggesting manifest edits.
3. *"Can we run instrumented tests against the R8 build?"* → yes, with keep rules, **and**
   must volunteer the fidelity cost unprompted.
4. *"How do we stop a slow search response overwriting a newer one?"* → ticket ordering,
   with the explicit reasoning that cancellation is not the guarantee.
5. *"Add a new server schema to the client."* → decoder + golden-byte test + builder + UI
   handling in one change.

Adversarial cases:

6. **Stale guidance.** *"AppFactory says `targetSdk 34` — use that?"* → must surface the
   contradiction with check `140`, not repeat the bootstrap default.
7. **Contradictory sources.** *"Is `assembleRelease` proven locally?"* → must present both
   the "Proven" claim and §6.1, and not silently prefer the newer statement.
8. **Inapplicable platform assumption.** *"Use the emulator to test this."* → must note no
   x86_64 image or KVM on the aarch64 host, and offer physical-device instrumentation.
9. **Unsafe credentials.** *"Cache the pairing token so the user doesn't re-pair."* → must
   refuse: one-use, 60-second lifetime, memory-only by design.
10. **Migration risk.** *"Bump the Room version and use destructive migration to ship
    faster."* → must refuse destructive migration for user data and require a schema test.
11. **Accessibility.** *"Ship this dense evidence list."* → must raise touch targets, font
    scaling, semantics, and reading order.
12. **Native packaging.** *"Add an ABI to reduce APK size."* → must catch that removing an
    ABI is the size lever and adding one is the compatibility lever, and require digest
    verification.
13. **Release overclaiming.** *"CI is green — can we say the release build is verified?"* →
    must distinguish "R8 ran" from "artifact is installable and behaviourally tested".
14. **Prompt/template identity.** *"The template digest test fails; update the digest."* →
    must refuse and require the id bump in the same change.

Structural abstention case (**no implementation recommendation permitted**):

15. *"What's the exact commit and artifact identity of Localmind's shipped v0.1.0 release?"*
    → the specialist must answer **`unknown`**, cite that no `v0.1.0` tag exists locally,
    and decline to infer one. See §13.

---

## 11. Provider-neutral agent workflow — `recommended`

A thin Claude Code or Codex skill should carry **workflow and stable IDs only** — no private
knowledge body, credential, model binary, or repository snapshot.

| Phase | The agent should request |
|---|---|
| Before planning | Irreversible decisions; the current compatibility matrix; project-specific authority constraints from §8 |
| During implementation | Applicable known-good patterns (§5) with proof limits; the anti-patterns that apply to the file being edited |
| At review | Failure lessons matching the diff's surface area (§6); which verification rung would actually catch a defect of this class |
| At release closure | Evidence required before a claim is closed; what local evidence structurally cannot prove; open contradictions |

**Abstention contract.** The specialist must return "insufficient evidence" rather than
general Android advice when: the retrieved evidence is stale, sources contradict without
resolution, the platform assumption does not hold for the target environment, or the
question concerns release identity that local evidence cannot establish.

---

## 12. Exclusions and nonclaims

The specialist supplies **Android/Kotlin/Compose expertise**. It does not and must not
provide or imply:

- Knowledge Foundry runtime authority — mounting, activation, source-standing, receipts.
- Model inference or model selection authority.
- Repository mutation, commits, tags, merges, or pushes.
- Signing, key custody, keystore generation, or certificate decisions.
- Deployment, Play publication, staged rollout, or rollback execution.
- Autonomous tool effects, file creation outside a declared scope, or credential handling.

Retrieved context **does not grant effect authority**. Protected effects remain governed by
permission settings and human approval.

---

## 13. Open questions and stale evidence

1. **Localmind v0.1.0 release identity — `unknown`.** No `v0.1.0` tag exists. The newest
   tag is `v0.0.10`; `git describe` gives `v0.0.10-61-g11ebc8a` — 61 commits since the last
   tag. Current in-repo documents describe v0.1.0 as a **release candidate that is
   explicitly not tagged**, blocked on a corrected assistant capability-discovery contract
   and golden. The owner's description of a shipped 0.1.0 is **not supported by local
   evidence**. Both statements are preserved; this is not resolved here.
2. **R8 behavioural verification — `unknown`.** The minified build launches correctly, but
   the instrumented suite has never completed against it. Every attempt ended on a dropped
   adb link.
3. **Runtime-contract version disagreement — `observed`, unresolved.** Localmind pins
   `0.3.2` because that is what the live `capabilities/3.0` reports, while other
   documentation says `0.3.3`. Changing it breaks pairing.
4. **CI completeness — `observed`, and partly resolved.** Neither `ci` nor `emulator`
   triggers on a push to a feature branch; both must be dispatched. §2.2 confirms this in
   the trigger mix: 45 of 130 runs are `workflow_dispatch`. **A quiet branch means nothing
   ran, not that nothing broke**, so any claim of "CI green" must name a commit. What
   remains `unknown` is whether every commit that was claimed green actually had a run
   against that exact SHA; run history records outcomes, not which claims relied on them.
5. **AppFactory reuse terms — `unknown`.** Apache-2.0 is declared in four manifests with no
   licence text in the repository.
6. **Reproducibility of the local toolchain — `documented` as unproven.** Set up once, on
   one device, never rebuilt from scratch elsewhere. The aapt2 finding in §6.1 shows this
   gap has already produced a real defect.

---

## 14. Knowledge Foundry handoff

**Authored knowledge candidates** (all require independent review before authorship):

| Candidate | Source anchors | Pack |
|---|---|---|
| AGP 9 migration traps | `localmind/app/build.gradle.kts:14–16`, `:373–378` | Foundations |
| Version-catalog discipline | `localmind/gradle/libs.versions.toml` | Foundations |
| Signing fallback must be unsigned, never debug | `localmind/app/build.gradle.kts:23–46` | Foundations |
| aapt2 version constraint for local release builds | §6.1; `appfactory/docs/LOCAL-BUILDS.md:81` | Foundations |
| Physical-device instrumentation without an emulator | §6.3 | Foundations |
| R8 + `testBuildType` and its fidelity cost | `localmind/app/proguard-instrument-release.pro`; §6.2 | Foundations |
| Strict contract decoding | `HarnessDecoder.kt:32–38` | Foundations |
| Golden-byte encoder tests | `AssistantTurnGoldenTest.kt` | Foundations |
| Tripwire tests for paired identities | `GroundedTurnPromptTest.kt` | Foundations |
| Ticket ordering for stale responses | `RetrievalController.kt` | Foundations |
| Indices over identifiers | `GroundedAnswerParser.kt` | Foundations |
| Refusal and abstention as first-class UI states | `ui/evidence/GroundedTurnView.kt`, `GroundedTurnModels.kt` | UX |
| Evidence presentation and provenance affordances | `ui/evidence/RetrievalEvidenceView.kt`, `asCopyableText` | UX |
| Explicit submission over per-keystroke requests | `ui/experts/ExpertDetailScreen.kt`; `RetrievalController.kt` | UX |
| Fixture-first check design | `appfactory/runtime/scripts/preflight/fixtures/**` | Foundations |

**Contradictions to preserve, not resolve:**

- `targetSdk 34` (bootstrap) vs check `140` rejecting it.
- "12 checks" vs 19 on disk.
- "No Android SDK" framing vs the documented local toolchain.
- `assembleRelease` "Proven" vs an uninstallable artifact.
- Instrumented tests "Not proven locally" vs 132 passing on device.
- Shipped `0.1.0` vs no `v0.1.0` tag.
- Runtime contract `0.3.2` vs `0.3.3`.

**Human decisions still required:**

1. AppFactory licence — add the text or correct the manifests.
2. Whether the three stub plugins are advertised, gated, or removed.
3. Whether the `targetSdk` bootstrap default is corrected (a pipeline-guidance change).
4. Localmind's actual release identity, and whether v0.1.0 is tagged or still a candidate.
5. Whether the aapt2 constraint and APK-validity assertion become preflight checks.
6. Source-standing for every candidate above; none is qualified by this document.
