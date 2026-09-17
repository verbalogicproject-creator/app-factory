# Testing on the phone without adb: what works, and what preview-bridge and codex-aware add

Researched and built 2026-09-17 for appfactory v1.0.0.

**Question:** the on-device acceptance test was blocked on "the phone needs adb". Can
preview-bridge (MCP) or codex-aware remove that dependency, and what connections have been
missed?

**How to read this:**
- **[this phone]**: measured on the phone (Android 15), with a receipt or a commit.
- **[code]**: read from source, with a file reference.
- **[inference]**: reasoning, not observed.

## Bottom line

**adb was never needed to test on the phone itself.** Termux, PRoot and every installed app
share the phone's loopback network. appfactory's web-shell already ships a command server
inside the app (`CommandServer.kt`, 127.0.0.1:8765), so a process in PRoot can reach it
directly. `adb forward` only matters when the test runs on a separate computer.

This is now built and proven:
- **`scripts/device-probe.sh`** installs through the user's tap, launches, and judges the
  rendered page.
- **App-declared checks** send commands and judge the observed effect, not the reply.
- **On this phone** it caught a real bug (a stuck note) on the old build and passed on the
  fixed one, confirmed by ear.

preview-bridge and codex-aware didn't replace adb. What they contributed was **ideas**, not
code:
- From preview-bridge: a live event feed read through a cursor.
- From codex-aware: "a dispatched command isn't an effect; only an observed effect is".

Neither project fits as a dependency, for the reasons below.

## 1. What works without adb [this phone]

| Need | Without adb | Evidence |
|---|---|---|
| Install | `termux-open app.apk` opens the system installer; the user taps Install | Done four times this session |
| Is it installed | `pm list packages` works from PRoot (Termux's `pm`) | spike receipt `~/.appfactory/receipts/spike-adb-free-2026-09-17.txt` |
| Launch | Termux `am start --user 0 -n <activity>`; resolve the activity with `cmd package resolve-activity --brief --user 0 PKG` | Without `--user 0`: SecurityException in `handleIncomingUser`. The activity class is `com.verbalogix.sagshell.MainActivity`, **not** `<appId>.debug.MainActivity` |
| Deep link | `am start --user 0 -a android.intent.action.VIEW -d sagsynth://debug PKG` | Switches the surface **only if the app is already running**; on a cold start the page wasn't ready to receive it |
| Background / foreground | `am start ... -c android.intent.category.HOME`, then relaunch | Used by the audio checks |
| Rendered page | `GET /__sag/health`, `/__sag/dom` | Caught a stale install by comparing content-hashed bundle names |
| Page errors | `GET /__sag/diagnostics?since=N` | Added this session (cursor idea from preview-bridge) |
| Crash report | `GET /__sag/crash` | Added this session. `Android/data` isn't readable from Termux on Android 11+, so without this route the crash file needed `adb run-as` |
| Drive the app | `POST /__sag/command` | Played a full melody; reply median 31 ms, max 102 ms |
| App telemetry | `GET /__sag/observe` | Audio: pitch, level, per-voice envelope, audio clock |

**Still needs adb (or Shizuku):**
- **Instrumented Espresso tests:** Termux `am` has **no `instrument` subcommand** ("Error: unknown command 'instrument'").
- **`dumpsys`:** denied, since the DUMP permission is missing.
- **Other apps' logcat.**

Self-adb over wireless debugging stays the optional `instrumented` stage. Shizuku with `rish`
is the alternative, but it has to be restarted after every reboot on a non-rooted phone
[source: shizuku.rikka.app].

**Can't be checked by any probe:**
- Pixels on screen.
- Sound from the speaker. The engine's telemetry proves what the audio graph produces, not
  what the ear hears.

Both stay with the user.

## 2. What was built (all committed)

**appfactory:**
- **Template** (`9711c49`):
  - The in-app server starts only in debug builds (`BuildConfig.DEBUG`), because loopback is
    shared with every app on the phone. Preflight check **220** enforces this.
  - The WebView is `destroy()`ed on release. It leaked one audio engine per relaunch, and
    three were observed at once.
  - `/__sag/crash` and the `since` cursor.
- **`device-probe.sh`** (`d4146d6`, `c61f724`):
  - Page verdict: loaded, zero failures, non-empty mount with height, attached WebView, no
    crash since launch, expected package, and not a stale bundle.
  - App checks from `.appfactory/device-checks.json`. Expectations: `status`, `signal_hz`,
    `voices_silent`, `voice_amp_above`, `level_db_below`, and `clock_rate_min` (the audio
    clock rate, a render-load signal where `renderCapacity` is absent, as it is in Chrome and
    WebView here).
  - An expectation the observation can't answer **fails**, never passes.

**SAG-synth** (`5d5dc87`, `02e7d7f`, `243f719`):
- Telemetry that says *what* the signal is: `signal_hz`, `dc_offset`, per-voice `voice_detail`,
  `context_time`.
- Every note is released when the page is hidden.

**sag-synth-apk** (`e07fe6c`): four audio checks.
- **Old build:** FAIL, "voice(s) still sounding, amp [0.24] -- a stuck note".
- **Fixed build:** PASS, and audible.

## 3. The audio case: how isolation found it

"SAG has no sound" survived several wrong guesses. What worked was **changing one thing at a
time and letting each test remove whole layers.** This is recorded because it's the method a
future "the app is broken on the phone" report should follow.

| Test | Result | What it ruled out |
|---|---|---|
| Engine telemetry | Running, -25 dB | "The engine is dead" |
| Chrome tab, plain Web Audio tone | Plays | Phone, speaker, Chromium audio |
| Same page inside an appfactory test app (WebView + foreground service) | Plays | WebView, app shell, template |
| Audio context created at page load, not on tap | Plays | "Autoplay before focus" |
| SAG's own bundle in Chrome | Plays | "SAG's page code can't make sound" |
| Pitch, DC offset and per-voice telemetry | A G4 held at sustain, read while the app was **in the background** | The real cause |

**Causes found:**
1. **Swiping away mid-press never delivers `pointerup`,** so the note stayed held.
2. **The telemetry was read while the app was backgrounded,** where it isn't heard.
3. **WebView leak:** separately, each relaunch added an audio engine.

**Wrong claims made along the way, so they aren't repeated:**
- "The 4 ms low-latency path is broken on this phone." Refuted in both Chrome and the WebView.
- "`renderCapacity` kills audio." It's absent on this phone.
- "Voices are never freed." `release()` does stop each voice's oscillators.
- "The process's audio link broke." A force-stop didn't fix it.

**A side finding from the melody test:** HTTP command jitter is up to 102 ms, which is
audible. A sequencer or piano roll must **send the pattern once and schedule it on the audio
clock.** In SAG that's the unimplemented `applySong` / transport; every log line already says
`applySong.transport is not implemented`.

## 4. preview-bridge [code: /data/data/com.termux/files/home/preview-bridge]

**What it is.** A Node MCP server with five **read-only** tools: event log, runtime errors,
long-poll tail, state snapshot, session info. A `__bridge.js` script in a page streams errors,
console output, form input, tracked clicks and route changes over a WebSocket. It's live in
this Claude Code session (leader on 127.0.0.1:5252, `/health` OK).

**Why it doesn't remove adb.**
- It observes a page; it can't install, launch or drive anything.
- appfactory's `/__sag` routes already capture console, failed loads and the rendered DOM from
  native code, so they don't depend on the page loading a script.

**Why it isn't a good fit inside the APK** [code + inference]:
1. **Port wiring bug:** `__bridge.js` dials port 5251 unless the page sets a global or meta
   tag (`public/__bridge.js:32-48`), while this machine's config serves 5253.
   `public/host.html:41-42` hardcodes 5250/5251 with no override.
2. **Mixed content:** the APK page's origin is `https://appassets.androidplatform.net`, and
   `__bridge.js` connects with plain `ws://127.0.0.1`. That may be blocked. Untested.
3. **No auth on the relay, and `Access-Control-Allow-Origin: *` on every HTTP endpoint**
   (`src/relay.ts:98-129`, `src/host.ts:20-24`), including captured form values. Any web page
   open on the phone could read them. On a shared-loopback phone this is a real leak.
4. **`query_preview_state` ignores its `selector` parameter** (`src/tools/previewState.ts:8,16`).
5. **Gaps in what it captures:** `replaceState` and `hashchange` aren't captured; custom event
   kinds can't be filtered or tailed (the zod enums reject them); the ring buffer is lost on
   leader failover; the in-page panel can't be turned off; when several pages are connected,
   the first reply wins.

**Adopted:** the `since` cursor on `/__sag/diagnostics`.

**Where preview-bridge does fit:** the **browser lane**, before an APK exists, with Vite in a
tab. Fix items 1, 3 and 4 in its own repo first.

## 5. codex-aware [code: github.com/verbalogicproject-creator/codex-aware @ 504ae98; local WIP at /data/data/com.termux/files/home/openai/codex-aware]

**What it is.**
- A FastAPI continuity API with a PostgreSQL or SQLite event log, a Next.js graph UI, and a
  Codex plugin with MCP tools: `aware_attach`, `aware_context`, `aware_graph`, `aware_act`,
  `aware_receipt`, `aware_refresh`.
- The loop is Observe → Ground → Resolve → Propose → Gate → Apply → Verify → Receipt.
- **Committed code** gates exactly one hard-coded policy proposal.
- **Local uncommitted work** (`control_plane.py`) adds application registration, command
  manifests with an `expected_effect`, state revisions, and receipts that succeed only when
  the app acknowledges the expected field value.

**Why it doesn't remove adb.** It has no device transport and no in-app SDK: nothing in either
tree embeds in an app. The only client is its own demo page. It lives at a layer above
testing: which actions an agent may take, and proof of what they did.

**What it gave:** the principle now enforced in `device_verdict.py`. **A command reply of
`"applied"` isn't evidence of an effect.** Every check judges `/__sag/observe`, and an
expectation that can't be observed fails.

**Gaps found** (worth fixing in codex-aware itself):
1. **Self-approval:** every paired actor, Codex included, is granted `proposal:decide`
   (`store.py:170`, `postgres.py:192`). Codex can approve its own proposal, which defeats the
   human gate. The attach response advertises only five scopes (`app.py:135`), which hides
   this.
2. **Unauthenticated effect reports:** `POST /effects` has no auth, and the observation is
   whatever the caller claims (`app.py:237-241`).
3. **Any approval unlocks a refresh:** `aware_refresh` checks that *any* `proposal.approved`
   event exists, not that *this* proposal was approved (`app.py:273-295`).
4. **The `aware.yaml` manifests are decorative:** the API never loads them. The graph is
   hard-coded in `seed.py`.
5. **Open public endpoints:** `/chatgpt/mcp` and `/ws/{workspace}` have no auth.

## 6. Connections not yet made

- **appfactory's `/__sag` channel is already a small codex-aware "application controller".**
  - Commands: `POST /__sag/command`.
  - Observed effects: `/__sag/observe`.
  - Identity: `instance_id`, plus package and sha on `/health`.

  With the device-checks format, `expected_effect` already exists on both sides. A codex-aware
  adapter for SAG would mostly map `SynthCommand`s to a manifest and `observe` to receipts.
  That turns "Codex plays and edits the synth" into a gated, receipted loop [inference].
- **Codex writing music needs the transport, not faster HTTP.** Pattern in, audio-clock
  scheduling, then device-checks that assert the pitches and timing that played. Today's
  harness is that test suite's first half.
- **Shared-loopback security applies to every local server in the estate:**
  - preview-bridge's `CORS *`
  - codex-aware's open `/ws`
  - appfactory's own server (now debug-only)

  The same rule and check (preflight 220's idea) belongs wherever a phone runs a localhost
  service.
- **The acceptance test no longer waits on adb:**
  1. `/android-dev`
  2. `webdetect`
  3. scaffold
  4. ladder
  5. the user installs
  6. `device-probe` green, plus the user's eyes

## Sources

- appfactory: `plugins/appfactory-core/runtime/scripts/device-probe.sh`, `runtime/bin/device_verdict.py`, `runtime/templates/kinds/web-shell/…/CommandServer.kt`, commits `9711c49`, `d4146d6`, `c61f724`
- SAG-synth: `/root/projects2/SAG-synth`, commits `5d5dc87`, `02e7d7f`, `243f719`; sag-synth-apk `e07fe6c`
- preview-bridge: `/data/data/com.termux/files/home/preview-bridge` @ `2e9966c`
- codex-aware: https://github.com/verbalogicproject-creator/codex-aware
- Android background activity starts: https://developer.android.com/guide/components/activities/background-starts
- Shizuku: https://shizuku.rikka.app/guide/setup/
- TermuxAm: https://github.com/termux/TermuxAm (the missing `instrument` was observed here, not read from its source)
