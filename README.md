# appfactory

A Claude Code marketplace that turns an app idea into a **signed, installed, running
Android APK** — from a terminal, with or without a local Android SDK.

```
/plugin marketplace add verbalogicproject-creator/appfactory
/plugin install appfactory-core@appfactory
/appfactory-core:bootstrap
```

---

## The constraint everything follows from

This was built on an aarch64 phone under Termux and PRoot. Google ships Android
build-tools as x86_64 binaries only, so nothing could compile locally:

**GitHub Actions was the compiler.** Every build was a push, and every push cost
2–5 minutes.

That single fact reshaped the whole design. When a round trip is minutes, the thing
worth optimising is not build speed but **time-to-failure** — how fast a mistake is
caught, and how far up the chain it can be caught. Hence a 2-second static check corpus
that runs before `git push` is even allowed to proceed.

### The constraint has since been lifted, and the design still holds

It was stated here as three blockers — x86_64 build-tools, JDK 25, Gradle 4.4.1. Two of
those were never blockers, and the third had a fix:

| Claimed blocker | What was actually true |
|---|---|
| local `java` is JDK 25 | JDK 25 is the **default**, not the only JDK. `openjdk-17-jdk` installs from apt on arm64 and `JAVA_HOME` selects it |
| local `gradle` is 4.4.1 | that is the **system** gradle, which a project with a wrapper never invokes |
| build-tools are x86_64-only | true of **Google's** build. Third-party aarch64 builds of `aapt2` exist and work |

`docs/VERIFICATION.md` had already named the real blocker precisely — *"`aapt2` is the
only genuinely native blocker; Kotlin, KSP, R8 and Compose are all JVM"* — and
predicted the payoff. Both halves turned out to be right.

Measured on the conformance app, aarch64 phone, warm daemon:

| | before | now |
|---|---|---|
| typecheck a rename | 2–5 min (push) | **13–21 s** |
| unit tests | 2–5 min (push) | **~45 s** |
| release APK with R8 | 2–5 min (push) | **2 m 18 s** |

**None of the corpus becomes redundant.** Preflight still runs in 2 seconds against a
1-minute local compile, and the checks that matter most — Hilt wiring, a fabricated
font certificate, a signing key that drifts — are things that *compile perfectly* and
fail on a device. A faster compiler moves one class of error earlier; it does not touch
the class this project exists for.

What it does change is that **V2 exists now** — see `docs/LOCAL-BUILDS.md` for the
setup, and `docs/VERIFICATION.md` for where the new rungs sit. Local rungs are an
*addition* to CI, not a replacement: CI remains the only x86_64 build, and the only one
that runs on a machine other than the author's.

## What this exists to prevent

Nine consecutive green builds once shipped an app that crashed before rendering a
pixel. Every failure below is real, happened here, and is now structurally impossible
or caught in seconds:

| Failure | Why it survived review |
|---|---|
| `lifecycle-runtime-compose` imported, never declared | compiles locally, fails in CI |
| `proguard-rules.pro` referenced, absent | build file lies quietly |
| `shrinkResources` instead of `isShrinkResources` | Groovy spelling in a Kotlin DSL |
| `@HiltAndroidApp` missing | **compiles clean, crashes at launch** |
| a fabricated font certificate | **compiles clean, crashes at launch** |
| release APK signed with the runner's throwaway debug key | different key each run; the installed cohort becomes permanently unupgradable, and nothing says so |
| `upload-artifact` matched nothing and went green | `if-no-files-found` defaults to `warn` |
| ProGuard keep rules written from memory | valid but incomplete — works until the case you didn't test |
| instrumented tests run against `debug`, so an R8 assertion never met R8 | the test existed, ran, reported success, and verified nothing |

The last two are the dangerous class. **Code that is wrong will not compile. Config
that is wrong compiles, ships, and fails on someone else's device.**

## What you actually get

`bootstrap` takes an idea to a signed APK on a physical device before any feature code
exists — a walking skeleton that traverses the entire pipeline first, so that every
later failure is attributable to app code rather than to the pipeline.

`scaffold.py` generates two kinds: `compose` (default, the skeleton above) and
`web-shell` (a Compose host for a built web bundle, with a 127.0.0.1-only
command/observe HTTP surface — see [`docs/GETTING-STARTED.md`](docs/GETTING-STARTED.md#the-web-shell-kind)).

It runs in this order, and the order is the point:

1. **Immutable decisions first.** Two things about an Android app have **no migration
   path at all** once a user installs: `applicationId` and the signing certificate.
   Change either and the installed copy cannot upgrade — it becomes a different app.
   These are settled before anything else is built.

   The persisted schema is a third decision settled here, but it is **migration-
   sensitive rather than immutable**: it *can* change, which is what migrations are
   for. What cannot be undone is that data already sits on devices, so a wrong
   migration destroys it. A different risk, and worth a different word.
2. **Generate and verify locally** — 21 static checks, ~2 seconds.
3. **Key into an encrypted vault, with a blocking backup step.** Losing a release key
   means you cannot ever update the installed cohort. There is no recovery.
4. **Push secrets and prove they arrived with a canary.** GitHub never returns a secret
   value, so `gh secret list` proves only that a *name* exists.
5. **Drive to a launched APK**, then report what is actually proven.

## The verification ladder

Each rung catches something no cheaper rung can. Cost is why the order matters.

| Rung | Cost | Catches uniquely |
|---|---|---|
| authoring hooks | ~0.2s | unpinned run lookups, secret material, pushing without preflight |
| static preflight | ~2s | 21 check classes |
| **local compile** | 13–21s | types, Compose compiler, KSP/Hilt graph |
| **local unit tests** | ~45s | logic, serialization, Room migration |
| **local lint** | ~75s | patterns that compile and fail later |
| **local R8 / minify** | ~2m20s | missing keep rules |
| CI compile + test + R8 | 2–4 min | **the same, on x86_64, on a machine that is not yours** |
| **emulator** | 6–12 min | **launch crashes** — the first rung that answers "does it run" |
| local instrumented (physical device over loopback adb) | ~1 min | real ABI, real OEM behaviour |
| physical device | manual | OEM behaviour, and the two worst bugs found here |

**A rung that has never been observed failing is not a rung.** Every one of these has
been deliberately broken and watched to go red. That discipline caught a rung claiming
coverage it did not have: the emulator rung was asserted to catch R8 failures in three
commit messages and a README table before anyone tested it — and it did not, because
`testBuildType` silently defaults to `debug`, where R8 never runs.

## The check corpus

21 checks, each shipping a fixture that reproduces its bug.

**`preflight.sh` refuses to run a check that has no fixture directory.** Not a
convention — the runner will not execute it. New checks are written fixture-first, and
step 2 is the one that matters: *run the existing preflight against the bug fixture and
confirm it PASSES*, proving the bug is currently invisible. A check that already fails
is redundant.

Three checks in this lineage passed while their own bug was present, all from patterns
that were very nearly right: a line-oriented grep against a multi-line block, an
alternation matching any `compose` artifact, and a case-sensitive prefix that missed
`testProguardFiles`. **Nearly right is the dangerous state** — it reports success and
ends the investigation.

Suppressions live in `.appfactory/preflight-ignore` as `<id> | <reason>`. The reason is
**mandatory**; an entry without one fails the run, and every active suppression prints
on every run. Silent suppression is how check corpora die.

## Plugins

One plugin, `appfactory-core`, with four skills:

| Skill | Status |
|---|---|
| `bootstrap` | present — walking-skeleton scaffold, described above |
| `plan` | planned in v1.0.0, not yet present — interview → `.appfactory/contract/` |
| `verify` | planned in v1.0.0, not yet present — the local ladder, preflight through release |
| `release` | planned in v1.0.0, not yet present — tag → CI → signed APK/AAB → cert pin → Play internal track |

The repository previously advertised three additional plugins
(`appfactory-plan`, `appfactory-ui`, `appfactory-build`) as manifest-only stubs. They
have been deleted rather than built out: `${CLAUDE_PLUGIN_ROOT}` is per-plugin, with no
cross-plugin path resolution and no dependency system, so shared runtime cannot live in
one plugin and be called from another — it must be vendored into the consuming repo by
the plugin that owns it. That made a multi-plugin split cost real duplication for no
independent value, so the work each stub described is being built as skills inside
`appfactory-core` instead.

## Secrets

`pass_manager.py` keeps an encrypted vault at `~/.appfactory/vault.json` (mode 0600),
which `init` and `doctor` **hard-refuse** to create inside a git worktree — enforced by
filesystem location, not by `.gitignore`. `cryptography` Fernet with scrypt, parameters
stored in the vault header so they can be raised later. The keystore *bytes* live in
the vault, so there is one file to back up and no `.jks` on disk between builds.

Values arrive on **stdin only** — never argv, because `ps` exposes it, and never shell
history.

**Build-time and runtime secrets are different things and the pipeline says so.** A
release keystore never enters the APK and its loss is unrecoverable. A runtime API key
in an APK is *public the moment it ships* — `BuildConfig`, `resValue`, NDK-hidden
strings and R8 all merely raise extraction from seconds to minutes. So key-shaped
literals fail the build. The sanctioned exception is keys bound to package + signing
certificate fingerprint, which are useless when extracted.

## Honest status

**Proven:** `appfactory-core` generated [`localmind`](https://github.com/verbalogicproject-creator/localmind),
which went from nothing to a signed, installed, running APK across five tags — with a
tested Room migration and a certificate pinned and verified before each publish.

**Proven:** local aarch64 builds — compile, unit tests, lint and R8 — on the phone this
was built on, closing a gap this repo had documented as open since the start. See
[`docs/LOCAL-BUILDS.md`](docs/LOCAL-BUILDS.md).

**Not proven:** the `plan`, `verify` and `release` skills — planned in v1.0.0, not yet
present; anything about multi-module projects. The check corpus is regex-shaped and
derived from single-module Compose apps, and is advertised as such. On local builds
specifically: no local emulator (needs an x86_64 image and KVM), no local signing, and a
toolchain assembled once, on one device, against one repo.

**Historical:** [`appfactory-conformance`](https://github.com/verbalogicproject-creator/appfactory-conformance)
was a separate repo (v0.0.2) used to check `bootstrap`'s scaffold against a
byte-for-byte reproduction. It is frozen; the factory's own CI building its scaffolded
demo app is planned to supersede it in v1.0.0.

**Top maintenance risk:** version rot. AGP, Kotlin, KSP and Compose form a tight
compatibility lattice and runner images move underneath it. Version matrices are dated
and taken from official release notes rather than from "what compiled last time"; a
weekly scheduled conformance build is the canary.

## Documentation

| Document | Covers |
|---|---|
| [`docs/GETTING-STARTED.md`](docs/GETTING-STARTED.md) | install, first app, what each stage does |
| [`docs/VERIFICATION.md`](docs/VERIFICATION.md) | the ladder, and how each rung was falsified |
| [`docs/LOCAL-BUILDS.md`](docs/LOCAL-BUILDS.md) | building on aarch64 without CI — setup, measurements, and what is still unproven |
| [`docs/CHECKS.md`](docs/CHECKS.md) | the corpus, and how to add a check fixture-first |
| [`docs/SECRETS.md`](docs/SECRETS.md) | the vault, the canary, and the two kinds of secret |
