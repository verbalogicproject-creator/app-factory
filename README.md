# appfactory

A Claude Code marketplace that turns an app idea into a **signed, installed, running
Android APK** — from a phone with no Android SDK.

```
/plugin marketplace add verbalogicproject-creator/appfactory
/plugin install appfactory-core@appfactory
/appfactory-core:bootstrap
```

---

## The constraint everything follows from

Android build-tools are x86_64-only. This was built on an aarch64 phone under Termux
and PRoot, where the local `java` is JDK 25 and the local `gradle` is 4.4.1 — so AGP
8.3, which needs JDK 17 and Gradle 8.4+, is blocked three separate ways.

**GitHub Actions is the compiler.** Every build is a push, and every push costs
2–5 minutes.

That single fact reshapes the whole design. When a round trip is minutes, the thing
worth optimising is not build speed but **time-to-failure** — how fast a mistake is
caught, and how far up the chain it can be caught. Hence a 2-second static check corpus
that runs before `git push` is even allowed to proceed.

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

It runs in this order, and the order is the point:

1. **Immutable decisions first.** Two things about an Android app have **no migration
   path at all** once a user installs: `applicationId` and the signing certificate.
   Change either and the installed copy cannot upgrade — it becomes a different app.
   These are settled before anything else is built.

   The persisted schema is a third decision settled here, but it is **migration-
   sensitive rather than immutable**: it *can* change, which is what migrations are
   for. What cannot be undone is that data already sits on devices, so a wrong
   migration destroys it. A different risk, and worth a different word.
2. **Generate and verify locally** — 12 static checks, ~2 seconds.
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
| static preflight | ~2s | 12 check classes |
| CI compile | 2–4 min | types, Compose compiler, KSP/Hilt graph |
| unit tests | +30s | logic, serialization, Room migration |
| R8 / minify | +90s | missing keep rules |
| **emulator** | 6–12 min | **launch crashes** — the first rung that answers "does it run" |
| physical device | manual | OEM behaviour, and the two worst bugs found here |

**A rung that has never been observed failing is not a rung.** Every one of these has
been deliberately broken and watched to go red. That discipline caught a rung claiming
coverage it did not have: the emulator rung was asserted to catch R8 failures in three
commit messages and a README table before anyone tested it — and it did not, because
`testBuildType` silently defaults to `debug`, where R8 never runs.

## The check corpus

12 checks, each shipping a fixture that reproduces its bug.

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

| Plugin | Status |
|---|---|
| **`appfactory-core`** | complete and exercised — runtime, vault, state, hooks |
| `appfactory-plan` | scaffolded, empty |
| `appfactory-ui` | scaffolded, empty |
| `appfactory-build` | scaffolded, empty |

Three are empty **on purpose.** They are being extracted from the act of building a
real app rather than designed in advance, because a template hardened against imagined
problems is hardened against the wrong ones. The corpus grew 6 → 12 checks over the
course of building one app; every one of those six came from a failure that actually
happened.

There are four plugins rather than three for a mechanical reason:
`${CLAUDE_PLUGIN_ROOT}` is per-plugin, with no cross-plugin path resolution and no
dependency system. Shared runtime therefore cannot live in one plugin and be called
from another — it must be **vendored into the consuming repo** by the plugin that owns
it.

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

**Not proven:** that `bootstrap` reproduces the conformance repo byte-for-byte; the
three empty plugins; anything about multi-module projects. The check corpus is
regex-shaped and derived from single-module Compose apps, and is advertised as such.

**Top maintenance risk:** version rot. AGP, Kotlin, KSP and Compose form a tight
compatibility lattice and runner images move underneath it. Version matrices are dated
and taken from official release notes rather than from "what compiled last time"; a
weekly scheduled conformance build is the canary.

## Documentation

| Document | Covers |
|---|---|
| [`docs/GETTING-STARTED.md`](docs/GETTING-STARTED.md) | install, first app, what each stage does |
| [`docs/VERIFICATION.md`](docs/VERIFICATION.md) | the ladder, and how each rung was falsified |
| [`docs/CHECKS.md`](docs/CHECKS.md) | the corpus, and how to add a check fixture-first |
| [`docs/SECRETS.md`](docs/SECRETS.md) | the vault, the canary, and the two kinds of secret |
