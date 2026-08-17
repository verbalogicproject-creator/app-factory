# The check corpus

Nineteen static checks, roughly two seconds, run before `git push` is allowed to proceed.

Every one exists because a specific failure happened and cost a CI round trip or worse.
A check with no incident behind it is a guess, and is labelled as one.

## The corpus

| id | catches | the incident |
|---|---|---|
| 010 | version-catalog aliases that do not resolve | `libs.lifecycle.runtime.compose` used, never declared |
| 020 | `proguardFiles` / `testProguardFiles` naming an absent file | `proguard-rules.pro` referenced, not present |
| 030 | manifest `@resource` references that do not resolve | theme named in the manifest, never defined |
| 040 | imports of deleted symbols | a stale `GeminiApiClient` import |
| 050 | androidx sub-packages with no declared artifact | curated list, not a general rule — see below |
| 060 | `@AndroidEntryPoint` with no `@HiltAndroidApp` | **compiled clean, crashed at launch** |
| 070 | malformed XML resources | `--` inside an XML comment, which is illegal per spec |
| 080 | invalid workflow YAML | a flush-left heredoc inside `run: \|` |
| 090 | `@Database` version with no committed schema | migration test failed on device with a missing asset |
| 100 | workflows invoking scripts that do not exist | a path that survived a vendoring change |
| 110 | unrendered `{{PLACEHOLDER}}` in generated output | a literal `{{APPLICATION_ID}}` shipped in a script |
| 120 | HTTP code with no `INTERNET`; network config present but unwired | `Operation not permitted`, with a second bug hiding behind it |
| 130 | migration `ADD COLUMN` disagreeing with the exported schema | a default that differed between migration and schema |
| 140 | `targetSdk` below Play's submission floor | a release blocked at upload, after it was cut |
| 150 | native code without `jniLibs.useLegacyPackaging = true` | `.so` shipped but not extracted; directory-scanning loaders found nothing |
| 160 | Kotlin DSL importing `java.*` and shadowing a Gradle type | a build script that resolved the wrong `Properties` |
| 170 | `shrinkResources` in the Groovy form inside Kotlin DSL | silently not shrinking |
| 180 | `actions/upload-artifact` without `if-no-files-found: error` | a release that published nothing and said success |
| 190 | a packaged `.so` whose `DT_NEEDED` does not resolve | **`dlopen failed: library "libomp.so" not found`, on a device, everything else green** |
| 200 | an `androidTest` source reading a build-type-only source set | **a fixture in `src/debug` pinned the whole instrumented suite to one build type — and retired a verification rung on false evidence** |

Three of those deserve expansion, because they are the ones that teach something.

**080** cost a wasted release tag. GitHub names a run after the *file path* when the
YAML will not parse, and `--log-failed` returns "log not found" — so the failure looks
like an infrastructure problem rather than a syntax error in your own file.

**120** found two bugs stacked. The missing `INTERNET` permission was the visible one.
Behind it sat a `network_security_config.xml` that existed, was correct, and was never
referenced from `<application android:networkSecurityConfig>` — inert, and invisible
until the first bug was fixed.

**190** is the corpus's second demotion from the emulator rung, and the more instructive
one, because the emulator could never have made the catch at all.

Eight arm64 libraries declared `NEEDED libomp.so` and none of them shipped it. ggml links
against OpenMP on arm64; `libomp.so` belongs to the NDK, and a workflow running `cmake`
directly packages only what `cmake` wrote — where building through AGP would have collected
it. Build green, unit tests green, lint green, R8 green, eighteen preflight checks green,
and the app dies at the first `System.loadLibrary`.

**No x86_64 library declares that dependency**, because upstream enables OpenMP for arm64
only — and the emulator rung is x86_64. This was not a gap the emulator happened to miss; it
is one the emulator is structurally incapable of seeing. Finding it took a physical device,
a CI republish and a trust-anchor update. The check reads the same ELF header the loader
reads, in about a second, and covers `armeabi-v7a` and `x86` as well — ABIs that neither a
test device nor an emulator exercises here.

It states its own limit: it proves every dependency is *present*, not that the library
*loads*. A missing symbol inside a library that is present still gets through.

**200** is the corpus's first check against a failure of *evidence* rather than of code.

Two instrumented tests called a fixture living in `src/debug`. The debug suite compiled and
passed, so nothing looked wrong — but `src/debug` is not compiled for the release variant,
so the first attempt to run that suite against the minified build died in the Kotlin
compiler with `Unresolved reference 'debug'`, in a test file, naming a symbol rather than a
layout.

What makes it worth a check is the second-order damage. The project's build file recorded,
in a long and careful comment, that release instrumentation *"HANGS with no output until the
45-minute job timeout"* and concluded that behavioural testing of the minified variant was
unachievable — so R8 coverage was deliberately narrowed and the gap written down as
permanent. That conclusion was reasonable from the outside and wrong underneath: the run
never reached a device, because it never compiled. **A coupling like this does not just
break one run; it can retire an entire rung on evidence that was never gathered.**

The check flags only packages declared in a build-type source set and *not* also in `main`,
because a package in `main` is legitimately visible everywhere and flagging it would make
the check noise. It catches both the `import` form and the fully-qualified call with no
import — the second is what the real incident used, and an import-only pattern passes
straight over it. That is the same near-miss shape as the three failures in this corpus's
own history.

Preview fixtures belong in `src/debug`; that is what it is for. A fixture that *tests*
assert on belongs to the test source set. Keeping a small builder in both is the correct
outcome, not a DRY violation to refactor away.

## Post-build: is the artifact an artifact?

`scripts/verify-apk.sh` is not a preflight check — preflight runs before a build, and there
is no APK to look at. It runs after `assembleRelease` in both `ci.yml` and `release.yml`,
and answers the question every other rung skips: not *did the build step succeed*, but *is
the thing it produced installable*.

The incident: on an aarch64 host, `aapt2 2.19` packaged a release APK containing dex, native
libraries and assets — and **no `AndroidManifest.xml` and no `resources.arsc`**. The zip was
structurally intact, `unzip -t` reported no errors, R8 ran, `mapping.txt` was produced, the
file was the expected size, and the release workflow passed **ten times out of ten**. AGP's
own shrunk resource archive was correct; only the final merge lost them.

It was found by a human trying to install it, and the platform's error is
`INSTALL_PARSE_FAILED_UNEXPECTED_EXCEPTION: Failed to parse ...: AndroidManifest.xml` —
which names the manifest and sends the investigation to the wrong file entirely. `aapt2 2.20`
packages it correctly, so the check's failure message names the toolchain version rather
than the symptom.

It runs **before** the signing check in `release.yml`, deliberately. Signature verification
presumes a file the platform can already parse; on a malformed container it either fails for
a reason unrelated to keys or passes over an artifact nobody can install.

Its limit is stated in its own output: it proves the container is well-formed and parseable.
It does not prove the app runs, or that R8 kept what it needed. It exists precisely because a
narrow check — *"R8 ran and a file exists"* — was mistaken for a broad one.

## The fixture contract

**`preflight.sh` refuses to run a check that has no fixture directory.** Not a
convention — the runner will not execute it, and `000-checks-have-fixtures` enforces
the existence half during every ordinary run.

```
fixtures/<id>/
  bug/            a minimal tree reproducing the failure   -> check must exit 1
  fixed/          the same tree, corrected                 -> check must exit 0
  bug-*/          evasion variants                         -> check must exit 1
  README.md       the real incident this came from
```

There are 7 evasion fixtures, each from a real near-miss: `bug-comment-only` (an
annotation inside a comment satisfying a presence-grep), `bug-wrong-class`,
`bug-theme-mismatch`, `bug-test-proguard`, `bug-loose-match`, `bug-config-unwired`, and
`bug-wrong-abi` (the dependency *is* in the repo, in a different ABI directory — the loader
searches one ABI and does not fall back, so a repo-wide filename search passes it).

Fixtures may be binary where the defect is binary. 190's are real ELF objects, built with
`-nostdlib` so they declare no libc and `-Wl,-z,max-page-size=4096` because aarch64's
default 64K alignment made otherwise-empty files 66KB. They are about 5KB each.

`selftest.sh` runs every check against every fixture. It was itself falsified in all
three of its own failure modes before being trusted.

## Adding a check, fixture-first

Step 2 is the one that carries the lesson.

1. Write `fixtures/<ID>/bug/` — the smallest tree that reproduces the failure.
2. **Run the *existing* preflight against it. It must PASS.** That proves the bug is
   currently invisible. If it already fails, your check is redundant and you have just
   saved yourself writing it.
3. Write `fixtures/<ID>/fixed/`.
4. Write the check.
5. `selftest.sh` green — including every evasion variant.
6. `README.md` naming the real incident.

## Nearly right is the dangerous state

Three checks in this lineage **passed while their own bug was present**, all from
patterns that were very nearly correct:

- a **line-oriented `grep`** against a multi-line `proguardFiles` block — the pattern
  was right, the line orientation was not. Fixed with `perl -0777` slurp mode.
- an **alternation matching any `compose` artifact**, so a missing one was masked by a
  different one being present.
- a **case-sensitive prefix** that matched `proguardFiles` and missed
  `testProguardFiles`.

None of these look wrong. Each reports success and ends the investigation, which is
exactly what makes them worse than a check that obviously fails.

Two further self-inflicted variants: checks that **scanned themselves** and found their
own fixtures (twice — 010 found its own `bug/` trees, and 110 produced 15 findings of
which 14 were its own source and the renderer's).

## Check 050 and crying wolf

050 began as a general rule: any `androidx.` sub-package imported without a matching
artifact. It produced six false positives immediately, because the mapping from package
to artifact is not mechanical.

It was rewritten as a **curated list of traps that have actually bitten**. This is a
deliberate trade: less coverage, zero noise. A check that cries wolf gets ignored, and
an ignored check is worse than no check, because it still looks like coverage on a
table like the one above.

## Suppressions

`.appfactory/preflight-ignore`, one per line:

```
<check-id> | <reason>
```

The reason is **mandatory** — an entry without one fails the whole run — and every
active suppression prints on every run.

```bash
if [ -z "$reason" ]; then
    printf 'FAIL suppression of %s has no reason. Silent suppression is how check corpora die.\n' "$id"
```

The mechanism exists because of a genuine deadlock: check 090 requires a committed Room
schema for every declared `@Database` version, but the schema JSON is *generated by
KSP during the build*, and preflight gates the push that triggers that build. On a
device with no Android SDK it could not be generated locally either.

The way out was suppress-with-reason, push, let CI generate and upload the schema,
commit it, delete the suppression. A legitimate use — and precisely why the reason
field is required, so a temporary suppression cannot quietly become permanent.

**With a local toolchain the deadlock is gone.** KSP is a JVM compiler plugin and runs
natively, so `./gradlew :app:kspDebugKotlin` writes the schema straight into
`app/schemas/`. The version can be committed in the same commit that declares it and
the suppression is never needed. See [`LOCAL-BUILDS.md`](LOCAL-BUILDS.md).

**Testing that produced a hazard worth more than the fix.** A local KSP run regenerates
only the **current** `@Database` version. Run against a cleared `app/schemas/` at
version 4, it produced `4.json` and nothing else — versions 1, 2 and 3 were gone,
because a schema records what the database looked like *then* and nothing in the build
remembers that.

Those files exist only because they were committed at the time, and they are what
`MigrationTestHelper` reads to prove a migration works. Losing them does not fail the
build: it silently removes the ability to test any migration ever again, and the loss is
recoverable only from git.

**The historical schemas are source, not build output.** Never clear that directory to
"regenerate" it — the thing you want back is the one thing regeneration cannot produce.

## Scope

The corpus is regex-shaped and derived from single-module Compose apps. It is
advertised as such until a second project proves otherwise. Checks declare a `SCOPE`
and **skip loudly rather than pass silently** when it does not apply — a skipped check
that prints nothing is indistinguishable from a passing one.
