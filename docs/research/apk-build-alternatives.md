# Building Android APKs on the phone: the alternatives

Researched 2026-09-17 for appfactory v1.0.0. Question: what ways exist to develop and compile
APKs inside Termux and/or proot-distro Ubuntu on an aarch64 Android phone, and which fit an
app factory that wraps web bundles in a native WebView shell?

**How to read this.** Each claim is marked with what backs it:
- **[this phone]**: measured here, with a receipt.
- **[source]**: a primary source, linked.
- **[inference]**: reasoning from sources, not something observed.

Web sources were fetched on 2026-09-17 and can go stale.

## Bottom line

Keep what appfactory already does: Gradle and the Android Gradle Plugin (AGP) running a real
Android SDK, with the SDK's x86_64 `aapt2` replaced by the native aarch64 build from Termux.

- **It's the only option with full AGP behaviour.** Manifest merging, dependency resolution,
  R8, signing configs and the Play publisher plugin all work, and it compiles exactly what CI
  compiles.
- **Its one fragile point is known, pinned and checked by the ladder.** That point is `aapt2`.
- **Build in native Termux where possible.** Native Termux Gradle beat PRoot on the same tree.
- **CI's ARM runner is the fallback lane,** and it has been green since run `35183976083`.

Nothing surveyed is a better host for this factory. One thing is worth a spike, and a few are
worth knowing about; see the ranking.

## What this phone actually runs [this phone]

| Piece | Value |
|---|---|
| Host | PRoot Ubuntu 26.04 aarch64 inside Termux; 8 cores, 14 GiB RAM, disk ~97% full |
| JDK | 17 (`/usr/lib/jvm/java-17-openjdk-arm64` in PRoot; `$PREFIX/lib/jvm/java-17-openjdk` in Termux) |
| SDK | `/root/android-sdk`, build-tools 36.0.0, platform 36; Gradle 9.4.0 |
| aapt2 | Termux package `aapt2` 16.0.0.4-2 (reports 2.20), maintainer @termux, source `github.com/termux/android-build-tools`; wired via `android.aapt2FromMavenOverride` |
| Why not the SDK's aapt2 | It's an x86_64 binary; the SDK's 2.19 path also produced a release APK with no manifest (`docs/LOCAL-BUILDS.md` §4a) |
| zipalign | No aarch64 build in the SDK; `verify-apk.sh` skips the `-P` check on ARM and says so |
| Build host benchmark | Native Termux Gradle vs PRoot, same tree, shared cache: warm debug packaging **26.2 s → 11.5 s**, warm compile 49.4 s → 43.4 s (`~/.appfactory/receipts/phase0-bench.md`, 2026-09-13) |
| This session's builds | Scratch web-shell app on PRoot: compile 1 m 34 s cold, 18 unit tests, debug, verify-apk and R8 release all green |

## The alternatives

| # | Approach | Runs on aarch64 phone? | Status | Fit for a WebView-shell factory |
|---|---|---|---|---|
| 1 | **Gradle + AGP, native aarch64 aapt2** (current) | Yes [this phone] | Working; aapt2 pinned and version-checked | **Best.** Full AGP; same build as CI |
| 2 | Same, but build tools from third-party aarch64 SDK builds | Yes [source] | lzhiyong/android-sdk-tools: latest release v35.0.2 (release year not confirmed) | Fallback source for `zipalign`/`aapt2` if Termux's lags |
| 3 | Gradle in native Termux (no PRoot) | Yes [this phone] | In use as the `termux` build host over loopback ssh | Faster host for the same build. No NDK hosted on Termux [inference] |
| 4 | No-Gradle pipeline: `aapt2 compile/link` → `javac`/`kotlinc` → `d8` → `zipalign` → `apksigner` | Yes [source] | Hobby scripts (felix021 gist, rocket-pig, docsBuildAPKs); `d8` and `apksigner` are Termux packages | Only for a trivial single-module shell. No manifest merger, no dependency resolution; Ktor, Compose and Hilt are out of reach |
| 5 | **CodeAssist** (on-device IDE, own build engine) | Yes [source] | Not archived; releases to v3.20.0; issues active into Sept 2025; rewrite `CodeAssist-v3` exists | Worth a spike: it drives aapt2/d8/apksigner without Gradle. Gradle-script compatibility is partial by design |
| 6 | AndroidIDE → **Code on the Go** | Yes [source] | AndroidIDE archived Dec 2024. Code on the Go (App Dev for All) is its stated successor, "actively maintained and updated weekly" | Interactive IDE, not a factory. Useful for the user, not as a pipeline |
| 7 | Sketchware Pro | Yes [source] | Maintained community fork; v7.0.0 in 2025 | Visual blocks; wrong shape for programmatic web bundles |
| 8 | Capacitor / Cordova | Plausible [inference] | Maintained | They generate a Gradle project, so they inherit the aapt2 problem already solved in #1 and add a JS toolchain. No gain over the in-house web-shell |
| 9 | Bubblewrap (PWA → Trusted Web Activity) | Plausible [inference] | Maintained by Chrome Labs | Needs an HTTPS-hosted PWA and still runs a JDK + SDK build. A different product (the app is a browser tab), not an offline shell |
| 10 | Flutter in Termux | aarch64 only [source] | Community `.deb` builds; upstream issue flutter/flutter#109087 on Termux release builds | Different stack; rough edges |
| 11 | Tauri mobile | No [source] | Termux support is an open request (tauri-apps/tao#448) | Not viable |
| 12 | React Native | Unproven | — | Native modules need the NDK; same blocker as #3 |
| 13 | **GitHub Actions arm64 runners** | Off-device | Free public preview Jan 2025, GA for public repos Aug 2025, labels `ubuntu-24.04-arm` / `ubuntu-22.04-arm` [source] | **The fallback lane.** appfactory's `build-arm` job is green |
| 14 | Remote Gradle build cache | Off-device | Standard Gradle feature | Speeds repeats. Doesn't solve anything aapt2-shaped |

## Findings that change or confirm decisions

1. **The aapt2 problem isn't unique to this phone, and it's a moving target.**
   - F-Droid's build server broke when AGP 8.12.0-alpha08's aapt2 began requiring CPU
     instructions (BMI1, SSE4.1, SSSE3) its hardware lacked. It was resolved by a backport in
     AGP 8.13.2 plus a hardware upgrade [source: gitlab.com/fdroid/admin/-/issues/593].
   - The lesson carries over [inference]: an AGP bump can change aapt2's requirements silently.
     appfactory's ladder already refuses aapt2 < 2.20 for release (`local-build.sh`).
2. **The web research got aapt2 packaging wrong, and this phone corrected it.** The draft said
   Termux has no `aapt2` package, because `termux-packages/packages/aapt2` returns 404. The
   phone has package `aapt2` 16.0.0.4-2 installed, built from `termux/android-build-tools`
   [this phone]. `d8` and `apksigner` are also Termux packages [source]. `zipalign` is the one
   tool with no Termux or SDK aarch64 build in use here.
3. **Native Termux beats PRoot for Gradle.** PRoot intercepts syscalls with ptrace, which is
   costly for Gradle's file-heavy work. The 56% packaging gain is measured here, and the
   default build host is already `termux`.
4. **CodeAssist sidesteps the problem differently.** It never runs Gradle, so AGP's aapt2
   download never happens. That same design is why it can't run appfactory's
   `build.gradle.kts` (Compose, Hilt/KSP, Ktor, Play publisher) [inference]. A spike should
   answer one question: can it build the plain `web-shell` template's APK at all?
5. **Nothing here replaces CI for release.** On-device builds are for iteration. The signed
   release and Play upload stay on CI (V3), where toolchains are stock and reproducible.

## Ranking for appfactory

1. **Keep #1 on the `termux` host** (#3 as the host), with aapt2 pinned and version-checked.
2. **#13 GitHub arm64 as the fallback lane** when an AGP or aapt2 bump breaks local builds.
3. **Spike #5 CodeAssist** on the plain web-shell template. Timebox it, and don't adopt it
   without a green receipt.
4. **Know #2 (lzhiyong)** as a source for a native `zipalign` if the `-P` alignment check ever
   needs to run on ARM.
5. **#4 no-Gradle** only if a "tiny shell, zero dependencies" app kind is ever wanted.
6. **Skip #6 to #12** for the factory. #6 (Code on the Go) is still a reasonable IDE for the
   user to try by hand.

## Unverified or open

- **GitHub arm64 runners for private repos:** a January 2026 date appeared in secondary
  sources only. Unverified.
- **lzhiyong/android-sdk-tools:** the year of the v35.0.2 release wasn't resolved.
- **soobujmiah/adt:** claims aarch64 build-tools 35–37 and "real device validation". The
  README reads as self-promotional, and commit history and binaries weren't checked. **Don't
  rely on it** without inspecting it directly.
- **Shizuku:** the latest stable release seen is v13.6.0 (2025-05-25), and it must be
  restarted after every reboot on non-rooted phones [source: shizuku.rikka.app]. Relevant only
  to instrumented tests; see `adb-free-device-testing.md`.

## Sources

- F-Droid aapt2 CPU requirement: https://gitlab.com/fdroid/admin/-/issues/593
- GitHub arm64 runners: https://github.blog/changelog/2025-01-16-linux-arm64-hosted-runners-now-available-for-free-in-public-repositories-public-preview/ and https://github.blog/changelog/2025-08-07-arm64-hosted-runners-for-public-repositories-are-now-generally-available/
- Termux packages: https://github.com/termux/termux-packages (apksigner, d8), https://github.com/termux/android-build-tools (aapt2)
- lzhiyong/android-sdk-tools: https://github.com/lzhiyong/android-sdk-tools/releases
- CodeAssist: https://github.com/tyron12233/CodeAssist
- AndroidIDE and its successor: https://androidide.com/ and https://github.com/appdevforall/CodeOnTheGo
- Sketchware Pro: https://github.com/Sketchware-Pro/Sketchware-Pro/releases
- Bubblewrap: https://github.com/GoogleChromeLabs/bubblewrap
- Capacitor CLI: https://capacitorjs.com/docs/cli/commands/build
- Flutter on Termux: https://github.com/flutter/flutter/issues/109087
- Tauri on Termux: https://github.com/tauri-apps/tao/issues/448
- Gradle build cache: https://docs.gradle.org/current/userguide/build_cache.html
- No-Gradle pipeline example: https://gist.github.com/felix021/e7179596244ee81852c646f904adddf6
