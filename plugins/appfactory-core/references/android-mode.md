# android-dev mode is ON

Android work in this project goes through the appfactory pipeline. The facts below are
device-specific and expensive to rediscover; they are injected because an agent that
guesses at them fails in ways that look like something else.

## Never run bare `./gradlew`

```bash
bash scripts/local-build.sh [--host proot|termux|auto] [--until STAGE] [STAGE...]
```

It exports the toolchain, writes `local.properties` for this host, picks the build host,
times each stage and writes a receipt. A bare `./gradlew` in a fresh shell picks JDK 25,
fails, and names the wrong JDK in the error.

Stages, cheapest first, each catching what no cheaper one can:
`preflight` (~5 s, 21 checks) → `compile` → `unit` (fails on 0 tests) → `lint` →
`debug` → `verify-apk` → `instrumented` (real phone) → `release` (R8).
It stops at the first red rung. A later green never covers an earlier red.

## The toolchain, which is not on PATH

- JDK 17 lives at `/usr/lib/jvm/java-17-openjdk-arm64`. Bare `java` is JDK 25.
- SDK at `/root/android-sdk`. `JAVA_HOME` and `ANDROID_HOME` are **unset** in a fresh shell.
- `~/.gradle/gradle.properties` already points AGP at Termux's **aapt2 2.20**. Never move
  that line into a repo: CI is x86_64 and the path is this machine's.
- **aapt2 2.19 silently packages a release APK with no AndroidManifest.xml and no
  resources.arsc.** The zip is valid, R8 runs, the device blames the manifest. The
  `release` stage refuses to run below 2.20.

## Build host

Default is **native Termux**, not this PRoot (measured: warm debug packaging 26.2 s →
11.5 s). It needs sshd on 8022 and `APPFACTORY_TERMUX_ROOTFS`. If sshd is down,
`--host termux` exits 1 — which reads like a broken build. Use `--host auto` when unsure;
it falls back to proot and says so.

## Only the DEBUG APK is installable locally

Local release builds are **unsigned**. Do not promise a release APK from this machine.
The installable artifact is `app/build/outputs/apk/debug/*.apk`, and instrumented tests
run against it. A signed release comes from CI, via a tag.

Device work: `bash scripts/device-instrument.sh` does the whole ritual. It installs both
APKs (a stale pair produces phantom `NoSuchMethodError`), derives the test package from
the APK rather than the applicationId (the debug suffix makes it `<id>.debug.test`),
zeroes the animation scales and restores them, and fails on zero tests. The wireless
port rotates; `adb connect localhost:<port>` with the **SDK's** adb, not Termux's.

## Decisions that cannot be undone

`applicationId` and the signing certificate have **no migration path** after the first
install. The persisted schema version is migration-sensitive. Settle them before code:

```bash
python3 .appfactory/bin/contract.py init --out .appfactory/contract \
    --application-id <id> --app-name "<name>" [--kind web-shell --web-dir <dist>]
python3 .appfactory/bin/contract.py validate .appfactory/contract
```

**Never type a targetSdk.** `contract.py target-sdk-floor` reads the dated Play table
inside preflight check 140. minSdk 28.

## Versions are adopted, never derived

`runtime/versions/2026-08-api36.toml` is the lattice: AGP 9.0.0, Gradle 9.4.0, Kotlin
2.3.0, KSP 2.3.4, Compose BOM 2025.09.01, Hilt 2.59, Room 2.8.3, Ktor 3.2.0, JDK 17,
compileSdk/targetSdk 36, minSdk 28.

Adding a dependency means finding a project that already builds AND RUNS with that
combination. Picking the newest of each artifact produced three CI round trips of
one-incompatibility-at-a-time. Ktor 2.3.11 compiled, packaged, passed all 21 checks and
threw `NoSuchMethodError` in `onCreate`, because coroutines 1.9 deleted an internal it
called. **Compiling is not the bar. Running is.**

Three AGP 9 rules a generated app already handles: do not apply
`org.jetbrains.kotlin.android`; `kotlinOptions {}` is gone, use a top-level
`kotlin { compilerOptions { jvmTarget = JvmTarget.JVM_17 } }` as an assignment; the R
class is non-final, so `when (id) { R.id.x -> }` breaks.

## Which kind

- Existing Kotlin or an `app/` module → adopt it, do not scaffold over it.
- A web project with a **built** bundle (`index.html`) → `--kind web-shell`.
- Neither → `--kind compose`, a walking skeleton first, features after.

`--web-dir` must point at a BUILT bundle, not a source tree.

## Evidence discipline

- A receipt is about **one tree**. `dirty: true` means it is not coverage. Commit, then
  re-run the rung you are about to claim.
- Preflight costs ~5 s against a 2-5 minute CI round trip. Run it before every push. A
  suppression in `.appfactory/preflight-ignore` needs a written reason.
- `gh run list` needs `--commit $(git rev-parse HEAD)` with the **full** 40-char sha. A
  short one returns an empty list with exit 0.
- `pass_manager.py canary` is the only proof a secret's VALUE arrived. `gh secret list`
  proves a name exists and nothing more.
- Robolectric has no ARM64 Linux runtime. Pure-JVM unit tests locally, instrumented tests
  on the phone, Robolectric in CI if at all.
- The vault is `~/.appfactory/vault.json`, outside every repo. Losing it is the one
  unrecoverable failure.

## How to work while this is on

Act on the fast rungs without asking: preflight, compile, unit, lint, a debug build.
**Ask first** before anything slow or irreversible — installing on the device, a release
build, a tag, a Play upload, or overwriting an existing project.

Deeper procedure lives in the skills, which are installed: `/appfactory-core:plan` for
the interview, `bootstrap` for a new app, `verify` for the ladder, `release` for a tag.
Read the one you need rather than reconstructing it.
