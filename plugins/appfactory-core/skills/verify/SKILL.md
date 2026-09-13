---
name: verify
description: Runs the local verification ladder for an appfactory-generated Android app on this machine and reads its receipts honestly — preflight, compile, unit, lint, debug APK, artifact check, instrumented tests on the physical phone over loopback adb, and the R8 release build — reporting exactly what each rung proved and nothing more. Use after any code change and before every push or tag; use it instead of pushing to find out whether something compiles.
allowed-tools: Bash, Read, Grep, Glob
---

# Verify an app locally

The ladder is ordered by cost so the cheapest rung that can fail is the one you read.
Every run writes a receipt. **A receipt is evidence about one tree**: it records the git
sha and whether the tree was dirty, and a claim made about a different tree is not
covered by it.

```bash
bash scripts/local-build.sh                       # preflight → compile → unit → lint → debug → verify-apk
bash scripts/local-build.sh instrumented          # + install both APKs on the phone and run androidTest
bash scripts/local-build.sh release               # + assembleRelease/bundleRelease, verify-apk, mapping check
bash scripts/local-build.sh --bench --until debug # timed, daemons restarted, all stages even after a failure
```

Stages and what each **uniquely** proves:

| Rung | Cost | Proves | Cannot see |
|---|---|---|---|
| `preflight` | ~5 s | 21 structural classes (see `docs/CHECKS.md`) | anything that needs a compiler |
| `compile` | 15-90 s | types, Compose compiler, KSP/Hilt graph | runtime behaviour |
| `unit` | 10-50 s | logic, wire formats; **fails on 0 tests** | Android framework, R8 |
| `lint` | 10-50 s | patterns that compile and fail later | — |
| `debug` | 10-90 s | a debug APK and an androidTest APK exist | that they install or run |
| `verify-apk` | <1 s | manifest + `resources.arsc` present, aapt2 parses it, 16 KB alignment | that the app runs |
| `instrumented` | ~1 min | **real ABI, real OEM, real ART** on this phone | other API levels |
| `release` | 2-3 min | R8 ran; mapping kept manifest classes; artifact is well-formed | that R8 kept what tests never touch |

Timings above are from this phone; `.appfactory/receipts/*.json` has the measured ones.

## Rules that cost real time to learn

1. **Fix, do not suppress.** A suppression in `.appfactory/preflight-ignore` needs a reason
   and prints on every run. If you cannot write the reason in one sentence, it is a bug.
2. **Assert the artifact, not the step.** `assembleRelease` exited 0 on an APK with no
   manifest. `verify-apk.sh` is why the `release` stage does not trust the exit code.
3. **Read the first red rung.** A later green never covers an earlier red; the script stops
   at the first failure for that reason (`--keep-going` is for benches only).
4. **Instrumented tests: build first, install both APKs, zero the animation scales.**
   `device-instrument.sh` does all three and restores the scales on every exit path. A
   stale app/test pair produced 68 `NoSuchMethodError` that looked like real failures.
5. **The debug test package is `<applicationId>.debug.test`** — the script reads it from
   the APK, never from the build file.
6. **Crashes may not be in logcat** on this ROM. The script prints `dumpsys dropbox` on
   failure; read that before guessing.
7. **Robolectric does not run here.** There is no ARM64 Linux native runtime. Keep pure-JVM
   unit tests and on-device instrumented tests local; Robolectric, if used at all, is CI-only.
8. **A green receipt with `dirty: true`** was made about a tree that no longer exists in
   git. Commit, then re-run the rung you are about to claim.

## Hosts

`local-build.sh` runs Gradle in this PRoot by default, or in native Termux over loopback
ssh with `--host termux` (needs `sshd` on 8022, JDK 17 in Termux, and
`APPFACTORY_TERMUX_ROOTFS` set to `$PREFIX/var/lib/proot-distro/containers/<name>/rootfs`).
The default lives in `~/.appfactory/build-host`, written after a measured benchmark —
never from a guess about which is faster.

## When the phone is not reachable

`device-instrument.sh` refuses rather than skips. Read the current port off Settings →
Developer options → Wireless debugging, then `adb connect localhost:<port>` (the SDK's
adb, not Termux's). Pairing persists; only the port rotates. The phone's own hotspot is a
sufficient Wi-Fi interface and is steadier than a network.

## What to report

State the rungs that ran, the sha they ran against, and what each proved. Say plainly
which rungs did **not** run. "Verified" without a receipt path is a claim, not evidence.
Local rungs are an addition to CI, never a replacement: CI is the only x86_64 build and
the only one on a machine that is not yours.
