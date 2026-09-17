#!/usr/bin/env python3
"""
device_verdict -- decide whether a web-shell app running on the phone actually works.

    device_verdict.py judge --health H.json --dom D.json --failures F.json --crash C.json
                            [--expect-pkg PKG] [--expect-sha SHA] [--launched-ms MS]
                            [--expect-index app/src/main/assets/web/index.html]

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
import sys


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
    args = ap.parse_args(argv)

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


if __name__ == "__main__":
    sys.exit(main())
