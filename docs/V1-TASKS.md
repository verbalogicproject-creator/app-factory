# v1.0.0 — task board

The live tracking list. Every status below was checked against the tree on the date
given, not read off a plan. When you change something, change the line here too.

**v1.0.0 closed: 2026-09-17.** Branch `v1.0.0` merged to `main` and tagged. Every must-do
for the release is in Done with its evidence; everything else is listed under
"Deferred to v1.1" with its reason.

Status key — `DONE` landed and verified · `OPEN` not started · `BLOCKED` waiting on
something outside the repo.

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
| M1a | Plugin-install receipt written | `~/.appfactory/receipts/plugin-install.txt` (2026-09-13). The board carried this as open for four days after it existed. |
| M2 | Status line wired into `~/.claude/settings.json`; fragment gained a composition path and 28 tests | this pass |
| G2 | `webdetect.py` — web project → built bundle | `runtime/bin/webdetect.py` (`detect` / `locate` / `build`), `runtime/data/web-frameworks.json` (@vercel/frameworks 3.34.0, 70 entries, Apache-2.0, provenance in NOTICE), `scripts/vendor-web-frameworks.mjs`, 29 tests + 1 scaffold test. **Parity:** detection matched upstream `@vercel/fs-detectors` 7.3.0 on 56 of 56 dirs (50 synthetic single-framework, 5 supersedes combos, SAG-synth's real `package.json`). **End to end:** a fresh `npm create vite` app (vanilla-ts, default config) → `webdetect.py build` → `npm run build` → fresh `dist/` located. Limits, stated in the file: a server-rendered app is refused, not converted; an `index.html` that calls a server passes; no monorepo walking; the 18 frameworks detected by `matchContent` alone had no synthetic parity fixture (sveltekit-1 was covered via a combo). |
| H0 | Hook and status-line stdin reads are bounded — an unbounded `cat` wedged the PRoot tracer and froze the session | `5dfcc0a`, `11b6335`, `tests/test_hooks_stdin_bound.py` |
| G1 | Asset handler root-mounted; the white-screen trap closed | `WebShellScreen.kt` `BundleRootPathHandler`, 13 tests. Proven against SAG-synth's real `dist/`: ladder green through debug, and every reference in the built `index.html` resolves to a path that exists in the APK. **The on-device rung has not run — no device attached.** |
| G1c/G1d | Instrumented rung on the device | 2026-09-14 on NX779J / API 35: `OK (6 tests)`; the page renders at full height |
| V2 | Push and prove CI | Run `35183976083` (`a2bed2a`): self-check, x86_64 and ARM green, after four runs that found four real bugs (`03ae658`, `5d77f0a`, `a2bed2a`) |
| — | adb-free device testing | Loopback is shared on the phone: `device-probe.sh` + `device_verdict.py` + app-declared checks (`d4146d6`, `c61f724`). Replaces G5 (adb install stage) and makes G6 optional |
| — | Command server debug-only; WebView destroyed on release; `/__sag/crash`; preflight 220 | `9711c49`. The WebView leak stacked three audio engines on the phone |
| A1 | Audio on the phone, measured | SAG's silence was a note stuck by swiping away mid-press (SAG-synth `02e7d7f`) plus the WebView leak; audio device-checks FAIL on the old build and PASS audibly on the fixed one (sag-synth-apk `e07fe6c`). Telemetry now reports pitch, DC, per-voice state and the audio clock (`5d5dc87`, `243f719`). A4b/A4c confirmed on the device the same day |
| — | Research reports | `docs/research/apk-build-alternatives.md`, `docs/research/adb-free-device-testing.md` (`240969d`) |
| — | Generated-app CI | First real generated repo (sag-synth-apk) failed three ways; fixed with `scaffold.py --refresh-runtime`, the Ktor R8 rule and non-fatal report uploads (`bc62dae`). Its next run: preflight, ARM and R8 green; only the debug-APK upload failed on the account's artifact quota (re-run pending) |
| G1b | Preflight: bundle assets resolve | Check 230, 4 bug fixtures (`bc62dae`) |
| V1 | Docs honesty pass | `bcc337b`: shipped skills no longer "planned", six nonexistent `pass_manager` commands removed, hotspot claim marked disproved |
| M2a | The mode, on and off | 2026-09-17, fresh session in `v1-acceptance`: status line showed `● android-dev`, `off` removed it and wrote `enabled: false` (user screenshots) |
| ACC | **The single acceptance test** | 2026-09-17, a fresh session with none of this context: stock Vite 8 + React 19 → contract → `webdetect` build → scaffold → ladder green (receipt `134537Z`) → signed R8 release, cert MATCH (`132915Z`) → installed → `device-probe` PASS (`20260917T134730Z`) → the user saw the page ("Count is 9"). Report: `/root/projects/v1-acceptance-apk/completion-report.md` |
| ACC-fix | Template defects the acceptance run found | Outside links replaced the bundle (`LinkPolicy`, 10 tests); cold-start deep links dropped (`PendingLinks`, 5 tests); `singleTop` made a second activity (`singleTask`). Ported from the acceptance app into the template; UNVERIFIED claims no longer duplicate; skills scaffold web apps into a sibling folder |

---

## Deferred to v1.1

Nothing here blocks a working factory. Each keeps its original reason.

| # | What | Why deferred / note |
|---|---|---|
| G3 | `adopt` for an existing repo | `--refresh-runtime` covers keeping a generated app current; adopting a foreign repo is its own design |
| G4 | Preflight vacuity | Checks 020/150/170/210 pass when `app/build.gradle.kts` is absent |
| G6 | adb port discovery | Only for the optional `instrumented` stage now; `device-probe` needs no adb |
| G7 | Multi-module | `app/` is hardcoded |
| G8 | `--with-native` | Accepted and inert; make it refuse honestly or implement |
| G9 | Local signing | The acceptance run had to decode the keystore by hand; `pass_manager` has no export (finding 9) |
| G10 | Lattice expiry | Nothing warns when the version lattice ages |
| M2b | The mode on another existing project | M2a and the acceptance run covered the mode on a new one |
| M4 | `docs/CODEX-PORT.md` | Hand-off doc |
| A2/A3 | Effect-bypass cost, Faust spike | Only if headroom runs out; the audio clock check now measures it |
| V3 | Play internal track | **Blocked on Eyal**: the first manual AAB upload |
| L1/L2 | Reconcile the updates log; mine `verbalogix-companion` | See below |
| ACC-4 | Default build host `termux` fails when sshd is down | `local-build.sh` should fall back to `proot` and say so |
| ACC-8 | `vault.passphrase` stored beside `vault.json`, both in one Drive backup | **Security, user action first:** take the passphrase out of that backup. Then `pass_manager doctor` should flag it |
| ACC-10 | `verify_mapping.py` ignores `@JavascriptInterface` methods | R8 keeping the WebView bridge is unproven for release |
| ACC-11 | `device-probe` cannot force-stop for a clean process | Termux `am` has no `force-stop` |
| ACC-12 | No page-side bridge for plain web apps | `/__sag/command` answers "no page answered" until the web app installs `window.__sagNative` |
| CI-quota | sag-synth-apk debug-APK upload | Re-run after GitHub recalculates artifact storage |

### L2 note

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

**2026-09-17:** G2 landed, so the front half now exists — `webdetect.py build` took a
default-config Vite scratch app to a located, fresh `dist/`. The chain has still never been
run as one piece onto the phone.

**2026-09-17, later: PASSED as one piece.** A fresh Claude Code session with none of this
board's context ran the whole chain on a stock Vite 8 + React 19 app, onto the phone, with a
receipt per rung — see ACC in Done. It also found three template defects that every earlier
proof had missed (outside links, cold-start deep links, a duplicate activity); they are
fixed in the template (ACC-fix). That is what the test was for.
