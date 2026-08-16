# The check corpus

Twelve static checks, roughly two seconds, run before `git push` is allowed to proceed.

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

Two of those deserve expansion, because they are the ones that teach something.

**080** cost a wasted release tag. GitHub names a run after the *file path* when the
YAML will not parse, and `--log-failed` returns "log not found" — so the failure looks
like an infrastructure problem rather than a syntax error in your own file.

**120** found two bugs stacked. The missing `INTERNET` permission was the visible one.
Behind it sat a `network_security_config.xml` that existed, was correct, and was never
referenced from `<application android:networkSecurityConfig>` — inert, and invisible
until the first bug was fixed.

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

There are 6 evasion fixtures, each from a real near-miss: `bug-comment-only` (an
annotation inside a comment satisfying a presence-grep), `bug-wrong-class`,
`bug-theme-mismatch`, `bug-test-proguard`, `bug-loose-match`, `bug-config-unwired`.

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
