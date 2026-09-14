# v1.0.0 — task board

The live tracking list. Every status below was checked against the tree on the date
given, not read off a plan. When you change something, change the line here too.

**Verified against the tree: 2026-09-14.** Branch `v1.0.0`.
252 tests passing, `scripts/repo-check.sh` clean.

Status key — `DONE` landed and verified · `OPEN` not started · `PARTIAL` started,
named gap remains · `BLOCKED` waiting on something outside the repo.

---

## Done

| # | What | Evidence |
|---|---|---|
| P0 | Device substrate: adb over loopback, phantom killer off, Termux grants, 15→51 GB free | `~/.appfactory/receipts/phase0-*.txt` |
| P0 | Build host chosen by measurement — Termux 56% faster than PRoot on warm debug packaging | `receipts/phase0-bench.md`, `~/.appfactory/build-host` |
| P1 | The factory got a test runner, and it found real defects | `b28f82e`, `tests/` |
| P1 | Two guard blind spots closed (`git -C`, `cd &&`) | `b28f82e` |
| P2 | The local ladder wired, not just documented | `9530499` — `local-build.sh`, `device-instrument.sh`, `ladder.py` |
| P3 | Contract is a real file; canary exists; release path + Play upload + ARM CI leg | `e7e7f18` |
| P4 | 21st check (edge-to-edge), 16 KB ELF alignment, `--kind web-shell` proven on the phone | `b33a10d`, 4 instrumented tests green |
| P4 | Ktor 2.3.11 → 3.2.0 launch crash found and fixed — only the on-device rung caught it | `bc52030` |
| G0 | Guards rewired onto token parsing; they had started blocking legitimate commands | `3ba946a` — `hooks/cmdparse.py`, 48 tests |
| G0 | Blocked commands now say plainly that nothing in them ran | `3ba946a` — `NOTHING_RAN` |
| M1 | Plugin installed and enabled; guards observed blocking live | `~/.claude/settings.json` → `appfactory-core@appfactory: true` |
| M2 | `/android-dev` is a mode: state file + `UserPromptSubmit` anchor + `SessionStart(compact)` doctrine | `d898834`, 37 tests |
| M2 | Status line wired into `~/.claude/settings.json`; fragment gained a composition path and 28 tests | this pass |
| G1 | Asset handler root-mounted; the white-screen trap closed | `WebShellScreen.kt` `BundleRootPathHandler`, 13 tests. Proven against SAG-synth's real `dist/`: ladder green through debug, and every reference in the built `index.html` resolves to a path that exists in the APK. **The on-device rung has not run — no device attached.** |

---

## Open — M: the mode

| # | What | Size | Note |
|---|---|---|---|
| M1a | Write the missing `receipts/plugin-install.txt` | S | The plugin is installed and the guards demonstrably fire, but the plan's receipt was never written. A guard observed blocking and *not recorded* is the same gap the corpus criticises elsewhere. |
| M2a | Prove the mode end to end after `/reload-plugins` | S | On → status line shows it → `/context` shows the payload → off → injection stops → restart → still on → compact → re-asserts. **Registration changes need `/reload-plugins`; the mode is not live until then.** |
| M2b | Exercise the mode on a project that is not this one | S | The honest test. SAG-synth is the case Eyal described. |
| M4 | `docs/CODEX-PORT.md` — the hand-off | M | Confirmed absent. What the mode is, why a state file rather than a skill, the exact payload, and the map onto `~/.agents/skills`, `~/.codex/prompts`, `~/.codex/hooks.json`, profiles. Must flag the conflict with the Android protocol already in `~/.codex/AGENTS.md`. |

## Open — G: the gaps that make `/android-dev <a web app>` actually work

Ordered by how badly each breaks the stated use case.

| # | What | Size | Status verified 2026-09-13 |
|---|---|---|---|
| G1c | Run the instrumented rung on the device | S | **PENDING A DEVICE.** The APK and its androidTest APK are built and waiting. `WebShellTest` now asserts the bundle's absolute-path JS ran and its CSS applied — assertions that fail under the old mount. Until this runs, G1 is proven statically and by APK inspection, not by a page actually rendering. |
| G1b | Preflight check for absolute asset paths | S | **OPEN.** The factory now has 13 regression tests over the mount, but a *generated* project has no check that its own bundle's absolute paths resolve. That is still worth ~25 lines + fixtures. No maintained linter exists. |
| G2 | `runtime/bin/webdetect.py` | M | **OPEN.** No such file. Vendor `@vercel/frameworks` (Apache-2.0) as JSON for `buildCommand` + `outputDirectory`. Netlify's `framework-info` is deprecated; `@netlify/build-info` is the fallback. |
| G3 | `adopt` for an existing repo | M | **OPEN.** `scaffold.py` has no `adopt`; `--force` overwrites with no merge. Nothing maintained does template-overlay onto a foreign repo (`copier adopt` is an open issue), so this is ours — thin, and it refuses rather than guesses. |
| G4 | Preflight vacuity | S | **OPEN.** Checks 020/150/170/210 all `pass` when `app/build.gradle.kts` is absent. An adopted multi-module repo goes green while being entirely unexamined. This is the corpus's founding failure class pointed at itself. |
| G5 | `install` stage | S | **OPEN.** `ladder.py:31` STAGES has no `install`. Add `adb install` of the debug APK, and state plainly that a local *release* APK is unsigned and therefore not installable. |
| G6 | ADB port discovery | S | **OPEN.** Termux's adb ships without mDNS, so `adb mdns services` cannot work here. Parse `avahi-browse -tpr _adb-tls-connect._tcp` — confirm avahi installs first, fall back to the manual port with a clear message. |
| G7 | Multi-module | M | **OPEN.** `app/` is hardcoded. Use `./gradlew -q projects`; a `settings.gradle.kts` regex cannot be correct because the DSL is a real language. |
| G8 | `--with-native` | S | **OPEN.** `scaffold.py:216` accepts it, stores it as a template token, and does nothing. Make it real or make it refuse honestly. |
| G9 | Local signing | M | **OPEN.** Gradle's `signingConfig` needs a file. Decrypt from the vault to a short-lived path, sign post-build with bare `apksigner`, shred. |
| G10 | Lattice expiry | S | **OPEN.** Check 140 warns when its own table is stale; the version lattice is dated 2026-08-15 and nothing warns. |

## Open — A: audio (SAG-synth), decided 2026-09-14

Full reasoning and claim table: `/root/projects/sag-synth-apk/AUDIO-PLAN.md`.
Short version — the crackle campaign already happened, its fixes are in the bundle on the
phone, and the telemetry built to measure it has **never produced a reading on a device**
(4,813 observations, zero carrying `underrun_ratio`). So: measure, then decide.

| # | What | When |
|---|---|---|
| A0 | Tap `▶ start`, confirm `● live` — no sound is probably the gesture unlock | Now, no wifi needed |
| A1 | **Audio baseline on the phone** via `/__sag/observe` | **Rides with G1c** — same device, same sitting |
| A2 | `wet: 0` effect-bypass cost | Only if A1 shows effects-dependent underruns |
| A3 | Faust/Elementary spike | Only if A1 shows exhausted headroom; needs its own ADR |
| A4 | Register `window.__sagNative` in the shipped bundle | After A1. Without it `/__sag/command` cannot reach the synth — an agent can observe it but not play it |

## Open — V: finishing v1.0.0

| # | What | Size | Status |
|---|---|---|---|
| V1 | Docs honesty pass | S | **OPEN, confirmed.** `docs/PLUGIN-ROADMAP.md` still says `plan`, `verify` and `release` are "Planned in v1.0.0, not yet present" — all three exist. Also: README and `GETTING-STARTED.md` carry the same claim; `SECRETS.md` lists `pass_manager` subcommands that never existed; `LOCAL-BUILDS.md:239` asserts the phone's own hotspot is sufficient for wireless debugging, **disproved on this device, cause unknown — mark it, do not rewrite it.** |
| V2 | Push and prove CI | M | **OPEN.** `v1.0.0` has **no upstream** — never pushed. The ARM leg and the `build-demo` job have never run once. This is the only rung that cannot be tested locally and the most likely source of the next surprise. |
| V3 | Play internal-track acceptance | M | **BLOCKED** on one human step: the first manual AAB upload in Play Console, plus inviting the service account. |

## Open — L: the updates log has itself drifted

`appfactory-updates-log.md` tallies **15 entries, 13 open** — but it was written in Aug 2026
against the Localmind project, and work since then has closed some of them without the log
being updated. Entry 3 ("the verification ladder has no on-device rung") is the clearest
example: the rung exists, is wired, and caught the Ktor crash.

| # | What | Size |
|---|---|---|
| L1 | Reconcile the 15 entries against the tree; close what is closed, keep the evidence | M |
| L2 | **Mine `verbalogix-companion` for device knowledge** | M |

`/storage/emulated/0/Download/claude-projects/verbalogix-companion` is in NEITHER documented
root, and has now held the answer to two problems this project derived the hard way: the Ktor
1.8/1.9 coroutines skew, and the WebView layout-params bug that produced a zero-height page.

Be precise about what it is. It is **not** a model of a well-built repo by this factory's
standards: 13 Kotlin files, **zero tests**, and not under version control. What it is, is a
body of Android integration written against this exact device and proven by use —
`EngineWebView.kt` (WebView in Compose, done right), `LocalHttpServer.kt` and `TokenStore.kt`
(loopback HTTP with auth), `accessibility/` (a real AccessibilityService, gesture dispatch,
node serialisation), `capture/ScreenCaptureService.kt`, and `apm/AdvancedProtectionDetector.kt`.

So extract the **facts**, not the structure: each one becomes a template line, a preflight
check, or a lattice entry with its rationale. Searching this path belongs in the mode doctrine
too — twice is a pattern, not bad luck.

This is the drift the repo warns about everywhere else, in the repo's own backlog. Worth
noting rather than quietly fixing: a log of known gaps that overstates the gaps is still a
log you stop trusting.

---

## Order

```
M2a reload+prove ─► M2b other project
G1 root-mount ✔ ─► G1c on device ─► G2 webdetect ─► the "/android-dev <web app>" case works
G4 vacuity ─► G3 adopt ─► G5 install ─► G6..G10
V1 docs ─► V2 push+CI ──────────────────────────► V3 Play  (blocked on Eyal)
M4 codex doc, L1 log reconcile — any time
```

Critical path is now **G1c → G2**. G1 is done; what remains between the mode and the thing
Eyal actually asked for is confirming it renders on the phone, and detecting/building the
web project automatically instead of being handed a `dist/`.

## The single acceptance test

In a scratch Vite app with **default config and absolute asset paths**:

`/android-dev this is a web app I want an APK from` → interview → contract → framework
detected → bundle built and located → scaffold → ladder green → **APK installed on the
phone, launching, and rendering the real page**, not a white screen. A receipt per rung.

As of 2026-09-14 the back half of that chain is proven for SAG-synth: given its built
`dist/`, the ladder goes green through debug and every asset the page references resolves
inside the APK. What is still unproven is the page rendering on the device (G1c, no device
attached), and the front half — detecting the project and running its build without being
handed a bundle (G2).
