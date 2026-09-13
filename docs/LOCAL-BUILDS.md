# Local builds on aarch64

Android build-tools ship as x86_64 binaries, and this project was built on an aarch64
phone. For most of its life that meant **CI was the only compiler** and every build was
a `git push` costing 2–5 minutes.

That is no longer true. This document is how, what it is worth, and what is still
unproven.

## The diagnosis was already correct

`docs/VERIFICATION.md` said it before anything was attempted:

> `aapt2` is the only genuinely native blocker; Kotlin, KSP, R8 and Compose are all JVM.

That held exactly. `d8`, `r8`, `apksigner` and `lint` are shell wrappers over JAR files
and run on any JVM. `aapt2`, `aapt`, `zipalign` and `aidl` are native ELF binaries and
do not. Swap the four native ones and the toolchain works.

The two *other* blockers this repo claimed were never blockers at all:

- **"local `java` is JDK 25"** — JDK 25 is the default `java` on the PATH. `apt install
  openjdk-17-jdk` provides arm64 JDK 17, and `JAVA_HOME` selects which one Gradle uses.
  Nothing had to be uninstalled.
- **"local `gradle` is 4.4.1"** — that is the *system* gradle. A project with a Gradle
  wrapper never invokes it; `./gradlew` downloads and uses its own distribution.

Both were true statements that were not blockers, recorded next to one that was. Worth
noticing as a pattern: a real constraint listed beside two apparent ones makes the whole
set look more solid than it is, and nobody re-checks the list.

## Setup

Verified on: aarch64 Android phone, Ubuntu under PRoot, AGP 9.0.0, Gradle 9.4.0,
compileSdk 36. Roughly 3 GB of disk and one download of each artifact.

### 1. JDK 17

```sh
apt install openjdk-17-jdk           # arm64, from the ordinary repos
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-arm64
export PATH="$JAVA_HOME/bin:$PATH"
```

### 2. The SDK

`sdkmanager` is a Java program, so it runs natively. What it *installs* for build-tools
is x86_64, which step 3 fixes.

```sh
export ANDROID_HOME="$HOME/android-sdk"
mkdir -p "$ANDROID_HOME/cmdline-tools"
# commandlinetools-linux-<build>_latest.zip from dl.google.com
unzip commandlinetools-linux-*_latest.zip -d "$ANDROID_HOME/cmdline-tools"
mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest"

yes | "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" --licenses
"$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" \
    "platforms;android-36" "build-tools;36.0.0"
```

`platforms/` is JARs and XML — architecture-independent, nothing to replace.

### 3. Native aarch64 build-tools

From [`Lzhiyong/android-sdk-tools`](https://github.com/Lzhiyong/android-sdk-tools),
which publishes aarch64 builds of the native tools.

Confirm what you got before trusting it. ELF machine `0x3e` is x86_64, `0xb7` is
aarch64:

```sh
head -c 20 "$ANDROID_HOME/build-tools/36.0.0/aapt2" | xxd -s 18 -l 2 -p
```

Replace `aapt2 aapt zipalign aidl dexdump split-select`, keeping the originals as
`.x86_64.bak`. **Leave `d8`, `r8`, `apksigner` and `lint` alone** — they are JVM
wrappers and already work.

Version-check rather than trusting the release tag. The tag read `35.0.2`, but the
binary inside self-reported `2.19-20250916`, a build-tools-36-era aapt2 — which is why
it works against AGP 9 at all:

```sh
"$ANDROID_HOME/build-tools/36.0.0/aapt2" version
echo "" | "$ANDROID_HOME/build-tools/36.0.0/aapt2" daemon    # must print "Ready"
```

The daemon check is the one that matters. AGP drives `aapt2` in daemon mode, so a
binary that runs `version` fine and cannot start a daemon fails at the only thing it
will be asked to do.

### 4. The trap: AGP ships its own `aapt2`

**Replacing the SDK's `aapt2` is not enough, and the failure is misleading.** AGP
downloads a *separate* `aapt2` from Maven and prefers it over the SDK's. Everything up
to resource processing succeeds, and then:

```
Execution failed for task ':app:processDebugResources'.
> AAPT2 aapt2-9.0.0-14304508-linux Daemon #0: Daemon startup failed
  This should not happen under normal circumstances, please file an issue if it does.
```

The message names AGP's Maven artifact, not the SDK path anyone has been editing, and
suggests filing a bug. The fix is to point AGP at the native binary:

```properties
# ~/.gradle/gradle.properties
android.aapt2FromMavenOverride=/data/data/com.termux/files/usr/bin/aapt2
```

### 4a. The `aapt2` VERSION matters, and getting it wrong is silent

**Use `aapt2` 2.20 or newer.** `pkg install aapt2` in Termux provides
`2.20-android-16.0.0_r4`. The SDK's own `build-tools/36.0.0/aapt2` self-reports
`2.19-20250916` and **is not sufficient**, even though it is native aarch64 and passes
the ELF check above.

The difference appears only on the **release** path — `isMinifyEnabled` plus
`isShrinkResources` — where 2.19 packages an APK containing dex, native libraries and
assets and **no `AndroidManifest.xml` and no `resources.arsc`**.

Nothing announces it. The zip is structurally valid, `unzip -t` reports no errors, R8
runs, `mapping.txt` is produced, and the file is the expected size. The tools that would
tell you are the ones nobody runs on a local build:

```sh
aapt2 dump badging app-release.apk   # error: could not identify format of APK
apksigner verify app-release.apk     # Missing AndroidManifest.xml
```

The device's own error names the manifest —
`INSTALL_PARSE_FAILED_UNEXPECTED_EXCEPTION: Failed to parse ...: AndroidManifest.xml` —
which reads like a manifest bug and sends you to the wrong file.

AGP's intermediate is not at fault: the shrunk resource archive under
`app/build/intermediates/shrunk_resources_binary_format/release/` contains both files
correctly even under 2.19. Only the final merge loses them.

`scripts/verify-apk.sh` catches exactly this and now runs after `assembleRelease` in both
`ci.yml` and `release.yml`. Run it locally too:

```sh
bash scripts/verify-apk.sh app/build/outputs/apk/release/app-release.apk
```

### 5. `local.properties`

```properties
sdk.dir=/root/android-sdk
```

Already in `.gitignore` in every app this pipeline generates.

## Put the override in `~/.gradle`, never in the repo

This is the one instruction here that can break something for other people.

`android.aapt2FromMavenOverride` is an **absolute path to one machine's binary**. In
`gradle.properties` at the repo root it is committed, and then:

- CI runs on `ubuntu-latest`, which is **x86_64** — the path does not exist, and if it
  did it would be the wrong architecture
- every other contributor gets a path from someone else's home directory

Machine-specific configuration goes in `~/.gradle/gradle.properties`, for the same
reason `local.properties` is git-ignored and a keystore never enters the tree. The
repo describes the project; the home directory describes the machine.

## What this is worth

Measured on the conformance app, warm daemon, aarch64 phone:

| Task | Local | Was (CI round trip) |
|---|---|---|
| `compileDebugKotlin` | 13–21 s | 2–5 min |
| `testDebugUnitTest` | ~45 s | 2–5 min |
| `assembleDebug` | ~1 m | 2–5 min |
| `assembleRelease` (R8) | 2 m 18 s | 2–5 min |
| `lint` | ~1 m 15 s | 2–5 min |

First build after setup was 3 m 46 s, nearly all of it downloading the dependency graph
once.

The class of error this moves is the one the ladder always said it would: a missing
import, a renamed symbol, a wrong signature. Those cost a full round trip before and
cost seconds now.

**It also caught something the corpus could not.** Running `lint` locally surfaced
`UnrememberedGetBackStackEntry` — a Compose ViewModel scoped to a back-stack entry that
could be destroyed and recreated. It compiles, it usually works, and it fails
intermittently much later. That is a lint rule, not a preflight check, and it was
found because lint became cheap enough to run while writing the code rather than after
pushing it.

## Proven, and not

**Proven** — each observed on this device, on a real app:

- `compileDebugKotlin`, including KSP, Hilt and Room codegen
- `testDebugUnitTest` — 42 tests
- `assembleDebug` — installable APK, verified running on a physical device
- `assembleDebugAndroidTest` — test APK packages
- `assembleRelease` — **R8 runs**, produces a 23 MB unsigned APK and a 35 MB
  `mapping.txt`. **Read that as narrowly as it is written.** It says R8 ran and files
  appeared; it does *not* say the APK was installable, and on `aapt2` 2.19 it was not —
  see §4a. That sentence sat in this "Proven" list while the artifact it described could
  not be parsed by any tool. Assert the artifact, not the step:
  `bash scripts/verify-apk.sh <apk>`.
- `lint` with `abortOnError = true`
- **Instrumented tests on a physical device** — 132 tests, 0 failures, over
  wireless-debugging `adb` from inside PRoot. See "Instrumented tests without an
  emulator" below.

**Not proven** — stated because a documented gap is safer than an assumed rung:

- **Instrumented tests on an EMULATOR locally.** The emulator needs an x86_64 system
  image and KVM; neither exists here. That rung stays CI-only. **The emulator is not the
  only way to run instrumented tests, though — the physical device works, and that moved
  from this list to "Proven" above.**
- **Local signing.** The release build above is unsigned. The vault, the cert pin and
  the publish path have not been exercised locally.
- **Reproducibility.** This was set up once, on one device, against one repo. It has
  not been run from scratch on a second machine.
- **Durability across AGP versions.** It works because a third-party `aapt2` happens to
  be new enough for AGP 9.0.0. An AGP bump can outrun it, and the symptom will be the
  misleading daemon-startup error above.

## Instrumented tests without an emulator

The phone this builds on is also an Android device. `adb` can reach it over its own
loopback, so the instrumented rung is available locally after all — **132 tests, 0
failures**, on real hardware rather than an x86_64 emulator.

### Getting a connection

Wireless debugging needs a **Wi-Fi interface**, not a Wi-Fi *network*. The phone's own
portable hotspot is enough, and it is far more stable than joining a network — every drop
kills wireless debugging and rotates the port.

1. Settings → Developer options → **Wireless debugging** → on
2. **Pair device with pairing code** — once, ever:
   `adb pair localhost:<pairing-port> <code>`
3. Each session, read `IP address & Port` off that screen:
   `adb connect localhost:<port>`

Pairing persists in `~/.android/adbkey` and `adb_known_hosts.pb`; only the connect port
rotates. `adb mdns services` returns nothing from PRoot — no multicast — so the port has
to come off the screen. Use the **SDK's** `adb`; the Termux build lacks mDNS support.

### Running the suite

```sh
./gradlew assembleDebug assembleDebugAndroidTest      # build FIRST
adb install -r -d app/build/outputs/apk/debug/app-debug.apk
adb install -r -d -t app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
for k in window_animation_scale transition_animation_scale animator_duration_scale; do
    adb shell settings put global $k 0
done
adb shell am instrument -w <applicationId>.debug.test/androidx.test.runner.AndroidJUnitRunner
for k in window_animation_scale transition_animation_scale animator_duration_scale; do
    adb shell settings put global $k 1
done
```

The instrumentation package is `<applicationId>.debug.test`, not `<applicationId>.test`
— the debug build has `applicationIdSuffix = ".debug"`, and the test APK's package
carries that suffix plus `.test`. A scripted form of this sequence
(`scripts/local-build.sh instrumented`) is planned in v1.0.0; today it is copy-paste
shell.

Five things cost real time to learn:

- **Do not use `connectedAndroidTest` on an unstable link.** Gradle compiles for minutes
  before it looks for a device, and the connection dies first. Pre-build, then install and
  instrument directly — about a minute.
- **Install *both* APKs.** Skipping the install and running `am instrument` against
  whatever is already on the device produced **68 `NoSuchMethodError`** from a stale
  app/test mismatch, which reads exactly like real test failures. Gradle's
  `connectedAndroidTest` does this install for you; bypassing it bypasses that too.
- **Zero the animation scales.** Emulators boot with them at 0, phones run at 1, and
  Compose's `waitForIdle` never settles while animations run. Restore them afterwards.
- **Crashes may not be in logcat.** Some OEM ROMs filter it; app lines never appear. Use
  `adb shell dumpsys dropbox --print`, which is where the
  `NoClassDefFoundError: androidx.tracing.Trace` behind a "hanging" release-variant run
  was finally found.
- **A green run is evidence only about the tree it ran against.** A device pass carried
  forward across a later change is not coverage — that mistake put a broken assertion on
  a remote branch.

### What this rung does and does not add

It runs on **real hardware and the real ABI**, which the x86_64 emulator cannot, and it
needs no KVM. It is still **one device, one OS build, one API level**. The emulator rung's
value was never that it was an emulator — it was API-level breadth on a machine that is
not the author's. That reasoning is unchanged.

## This does not replace CI

CI stays, and not only as a fallback:

- it is the only **x86_64** build, and the only one on a machine that is not the
  author's
- it is the only place the emulator rung, signing, the cert pin and the release path run
- a local toolchain assembled by hand is exactly the kind of environment that drifts
  without announcing it

The honest framing is that the ladder gained rungs at the cheap end. The expensive
rungs still answer questions the cheap ones cannot, which was the point of ordering
them by cost in the first place.
