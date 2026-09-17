#!/usr/bin/env python3
"""
device_verdict -- decide whether a web-shell app running on the phone actually works.

    device_verdict.py judge --health H.json --dom D.json --failures F.json --crash C.json
                            [--expect-pkg PKG] [--expect-sha SHA] [--launched-ms MS]
                            [--expect-index app/src/main/assets/web/index.html]
    device_verdict.py checks --file .appfactory/device-checks.json --pkg PKG
                             [--base http://127.0.0.1:8765] [--am AM] [--cmd CMD]

Prints {"ok": bool, "reasons": [...], "warnings": [...]} and exits 0 when ok, 1 when not.

WHY THIS EXISTS. device-probe.sh reaches the app's own command server over 127.0.0.1 --
no adb: Termux, PRoot and every installed app share the phone's loopback. The shell does
the fetching; the judging is here, because "is this a white screen" is a decision, and a
decision that can be made pure is one pytest covers without a phone.

WHAT COUNTS AS WORKING. Every signal below has, on its own, been green on a broken page:
  - pageLoaded is true when every script 404'd (it means "navigation finished").
  - an empty failure list is compatible with a bundle that mounted nothing.
  - a mounted DOM can render into a zero-height box.
So all of them must hold: loaded, zero counted failures, a non-empty mount (or body) with
non-zero height, a WebView that is attached and laid out, and no crash since launch.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request


def bundle_scripts(index_html):
    """Basenames of the <script src> files an index.html loads -- content-hashed by Vite
    and most bundlers, so they identify the exact bundle build."""
    return sorted({os.path.basename(m.split("?")[0])
                   for m in re.findall(r"<script\b[^>]*\bsrc=[\"']([^\"']+)[\"']", index_html, re.I)})


def judge(health, dom, failures, crash, expect_pkg=None, expect_sha=None, launched_ms=None,
          expect_scripts=None):
    """expect_scripts: script basenames from the tree's packaged index.html. A LOCAL build
    stamps sha=local, so the sha cannot tell a stale install from a fresh one; the hashed
    bundle names can. (Found on the phone: sagshell ran index-Cm8fn7Mn.js while the repo
    shipped index-ChNv93mm.js, and every on-device "unverified" was about the old build.)"""
    reasons, warnings = [], []

    if not isinstance(health, dict):
        return {"ok": False, "reasons": ["no /__sag/health response -- server not reachable"], "warnings": []}

    if expect_pkg and health.get("pkg") != expect_pkg:
        reasons.append(f"health answered for {health.get('pkg')!r}, expected {expect_pkg!r} -- another app holds the port")
    if expect_sha:
        sha = health.get("sha")
        if sha == "local":
            warnings.append("app was built without a git sha (sha=local); cannot tie this run to a commit")
        elif sha != expect_sha:
            reasons.append(f"installed build is sha {sha!r}, expected {expect_sha!r} -- an older APK is installed")
    if health.get("pageLoaded") is not True:
        reasons.append("pageLoaded is not true -- navigation never finished")
    if health.get("pageFailures", 0) != 0:
        reasons.append(f"page reported {health.get('pageFailures')} failure(s)")

    if failures:
        for f in failures[:5]:
            reasons.append(f"page failure [{f.get('kind')}]: {f.get('message')} ({f.get('source') or '-'})")

    reasons.extend(_dom_reasons(dom, warnings))

    if expect_scripts and isinstance(dom, dict) and isinstance(dom.get("page"), dict):
        loaded = {os.path.basename(str(x).split(" [")[0].split("?")[0]) for x in dom["page"].get("scripts") or []}
        missing = [x for x in expect_scripts if x not in loaded]
        if missing:
            reasons.append(f"installed app is a different bundle build: tree expects {missing}, page loaded {sorted(loaded)} -- reinstall the fresh APK")

    if isinstance(crash, dict) and crash.get("present"):
        modified = crash.get("modifiedMs") or 0
        first = (crash.get("text") or "").splitlines()
        head = next((l for l in first if l and "=" not in l), "")[:200]
        if launched_ms is not None and modified >= launched_ms:
            reasons.append(f"app crashed during this run: {head}")
        else:
            warnings.append(f"a crash report from an earlier run exists: {head}")
    elif crash is None:
        warnings.append("no /__sag/crash response (app built before that route existed?)")

    return {"ok": not reasons, "reasons": reasons, "warnings": warnings}


def _dom_reasons(dom, warnings):
    if not isinstance(dom, dict):
        return ["no /__sag/dom response"]
    out = []
    host = dom.get("host") or {}
    page = dom.get("page")
    if host.get("attached") is not True:
        out.append(f"WebView not attached (host={host})")
    elif not host.get("height"):
        out.append("WebView has zero height")
    if not isinstance(page, dict):
        out.append("page did not answer the DOM probe (evaluateJavascript returned nothing)")
        return out
    if page.get("readyState") != "complete":
        out.append(f"document.readyState is {page.get('readyState')!r}, not 'complete'")
    if page.get("mountPresent"):
        if (page.get("mountChildren") or 0) <= 0:
            out.append(f"mount #{page.get('mountId')} is empty -- the bundle rendered nothing (white screen)")
        elif (page.get("mountFirstChildHeight") or 0) <= 0:
            out.append(f"mount #{page.get('mountId')} rendered into a zero-height box")
    else:
        warnings.append(f"no #{page.get('mountId')} element; judged on <body> instead (pass --mount to device-probe)")
        if (page.get("bodyChildren") or 0) <= 0:
            out.append("<body> has no children -- the page is blank")
        elif (page.get("bodyScrollHeight") or 0) <= 0:
            out.append("<body> has zero height")
    return out


# ---------------------------------------------------------------------------
# App-declared checks: send a command, observe the effect, judge the effect.
#
# A command the app ACCEPTED is not evidence it did anything ("applied" is a dispatch
# receipt, not an effect). Every step therefore judges what /__sag/observe reports after
# it, never the command's own reply alone. An expectation whose field the observation does
# not carry FAILS -- a check that passes because it could not see is the false green this
# exists to prevent.
#
# .appfactory/device-checks.json:
#   {"steps": [{"name": "...", "command": {...}?, "background": true?, "foreground": true?,
#               "wait_ms": 1200, "expect": {...}}]}
# expect keys:
#   status            the command reply's status, e.g. "applied"
#   signal_hz         [hz, tolerance_ratio]  latest observation's signal_hz within tolerance
#   voices_silent     true  every voice_detail entry has amp <= 0.001
#   voice_amp_above   x     at least one voice has amp > x
#   level_db_below    x     latest level_db < x (null = silent = below)
#   clock_rate_min    r     audio clock rate across the observations >= r
# ---------------------------------------------------------------------------
SILENT_AMP = 0.001


def clock_rate(observations):
    """Rate of context_time against observed_at across the window, or None if unmeasurable."""
    pts = [(o["observed_at"], o["context_time"]) for o in observations
           if isinstance(o, dict) and isinstance(o.get("context_time"), (int, float))
           and isinstance(o.get("observed_at"), (int, float))]
    if len(pts) < 2:
        return None
    (t0, c0), (t1, c1) = pts[0], pts[-1]
    wall = (t1 - t0) / 1000.0
    return None if wall <= 0 else (c1 - c0) / wall


def expectation_reasons(expect, reply, observations):
    reasons = []
    obs = [o for o in (observations or []) if isinstance(o, dict)]
    last = obs[-1] if obs else None

    if "status" in expect:
        got = (reply or {}).get("status")
        if got != expect["status"]:
            reasons.append(f"command status {got!r}, expected {expect['status']!r} (reply {reply})")

    needs_obs = [k for k in expect if k != "status"]
    if needs_obs and last is None:
        return reasons + ["no observation to judge (is /__sag/observe wired?)"]

    if "signal_hz" in expect:
        hz, tol = expect["signal_hz"]
        got = last.get("signal_hz")
        if not isinstance(got, (int, float)):
            reasons.append(f"no signal_hz in the observation -- expected ~{hz} Hz (silence, or the app does not report it)")
        elif abs(got - hz) > hz * tol:
            reasons.append(f"signal at {got:.0f} Hz, expected {hz} Hz +/-{tol:.0%}")

    if "voices_silent" in expect or "voice_amp_above" in expect:
        detail = last.get("voice_detail")
        if not isinstance(detail, list):
            reasons.append("observation has no voice_detail -- cannot judge voices")
        else:
            amps = [v.get("amp", 0) for v in detail if isinstance(v, dict)]
            if expect.get("voices_silent"):
                loud = [round(a, 3) for a in amps if a > SILENT_AMP]
                if loud:
                    reasons.append(f"voice(s) still sounding, amp {loud} -- a stuck note")
            if "voice_amp_above" in expect and not any(a > expect["voice_amp_above"] for a in amps):
                reasons.append(f"no voice above amp {expect['voice_amp_above']} (amps {amps}) -- the note did not start")

    if "level_db_below" in expect:
        lvl = last.get("level_db")
        if "level_db" not in last:
            reasons.append("observation has no level_db")
        elif lvl is not None and lvl >= expect["level_db_below"]:
            reasons.append(f"level {lvl:.1f} dB, expected below {expect['level_db_below']} dB")

    if "clock_rate_min" in expect:
        rate = clock_rate(obs)
        if rate is None:
            reasons.append("cannot measure the audio clock rate (needs two observations with context_time)")
        elif rate < expect["clock_rate_min"]:
            reasons.append(f"audio clock runs at {rate:.2f}x real time, expected >= {expect['clock_rate_min']} -- the render thread is falling behind")
    return reasons


def run_checks(steps, post, observe, background, foreground, sleep):
    """IO is injected: post(cmd)->reply, observe(n)->[obs], background(), foreground(), sleep(s)."""
    results = []
    for i, step in enumerate(steps):
        name = step.get("name") or f"step {i + 1}"
        reply = None
        try:
            if step.get("command") is not None:
                reply = post(step["command"])
            if step.get("background"):
                background()
            if step.get("foreground"):
                foreground()
            sleep(step.get("wait_ms", 1000) / 1000.0)
            observations = observe(step.get("observe", 4))
            reasons = expectation_reasons(step.get("expect") or {}, reply, observations)
        except Exception as exc:  # a broken step is a failed step, never a skipped one
            reasons = [f"step raised {type(exc).__name__}: {exc}"]
        results.append({"name": name, "ok": not reasons, "reasons": reasons})
    return {"ok": all(r["ok"] for r in results) and bool(results), "steps": results}


def _http(base):
    def post(cmd):
        req = urllib.request.Request(f"{base}/__sag/command", data=json.dumps(cmd).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read() or b"null")

    def observe(n):
        with urllib.request.urlopen(f"{base}/__sag/observe?tail={int(n)}", timeout=8) as r:
            return json.loads(r.read() or b"[]")
    return post, observe


def _load(path):
    if not path:
        return None
    try:
        with open(path) as fh:
            text = fh.read().strip()
        return json.loads(text) if text else None
    except (OSError, ValueError):
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="device_verdict.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    j = sub.add_parser("judge")
    for name in ("health", "dom", "failures", "crash"):
        j.add_argument(f"--{name}")
    j.add_argument("--expect-pkg")
    j.add_argument("--expect-sha")
    j.add_argument("--launched-ms", type=int)
    j.add_argument("--expect-index", help="the tree's packaged index.html, to detect a stale install")
    c = sub.add_parser("checks")
    c.add_argument("--file", required=True)
    c.add_argument("--pkg", required=True)
    c.add_argument("--base", default="http://127.0.0.1:8765")
    c.add_argument("--am", default="am")
    # dest renamed: `cmd` is the subcommand's own dest, and argparse would silently overwrite it.
    c.add_argument("--cmd", dest="cmd_bin", default="cmd")
    args = ap.parse_args(argv)

    if args.cmd == "checks":
        return _checks_main(args)

    expect_scripts = None
    if args.expect_index:
        try:
            with open(args.expect_index) as fh:
                expect_scripts = bundle_scripts(fh.read())
        except OSError:
            expect_scripts = None

    result = judge(
        _load(args.health), _load(args.dom), _load(args.failures) or [], _load(args.crash),
        expect_pkg=args.expect_pkg, expect_sha=args.expect_sha, launched_ms=args.launched_ms,
        expect_scripts=expect_scripts,
    )
    print(json.dumps(result, indent=1))
    return 0 if result["ok"] else 1


def _checks_main(args):
    with open(args.file) as fh:
        steps = json.load(fh).get("steps") or []
    post, observe = _http(args.base)

    def am(*a):
        subprocess.run([args.am, "start", "--user", "0", *a], capture_output=True, timeout=30)

    def background():
        # The launcher, not another app: generic, and it is what a swipe home does.
        am("-a", "android.intent.action.MAIN", "-c", "android.intent.category.HOME")

    def foreground():
        out = subprocess.run([args.cmd_bin, "package", "resolve-activity", "--brief", "--user", "0", args.pkg],
                             capture_output=True, text=True, timeout=30).stdout.strip().splitlines()
        if out and "/" in out[-1]:
            am("-n", out[-1])

    result = run_checks(steps, post, observe, background, foreground, time.sleep)
    print(json.dumps(result, indent=1))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
