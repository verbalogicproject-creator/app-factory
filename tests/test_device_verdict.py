"""Tests for runtime/bin/device_verdict.py -- the pass/fail decision behind device-probe.sh."""
from __future__ import annotations

import json
import subprocess
import sys

from tests.conftest import RUNTIME_BIN, load_module

dv = load_module("device_verdict", RUNTIME_BIN / "device_verdict.py")

HEALTH = {"pkg": "com.example.app.debug", "version": "0.0.1", "sha": "abc123", "pageLoaded": True, "pageFailures": 0}
# Shape taken from a real /__sag/dom response on the phone (2026-09-17, sagshell.debug).
DOM = {
    "host": {"attached": True, "height": 2381, "isLaidOut": True},
    "page": {"readyState": "complete", "mountId": "root", "mountPresent": True, "mountChildren": 1,
             "mountFirstChildHeight": 793.6, "bodyChildren": 1, "bodyScrollHeight": 794},
}
NO_CRASH = {"present": False, "path": "", "modifiedMs": 0, "text": ""}


def _dom(**page):
    return {"host": DOM["host"], "page": {**DOM["page"], **page}}


def test_a_working_page_passes():
    r = dv.judge(HEALTH, DOM, [], NO_CRASH, expect_pkg="com.example.app.debug", expect_sha="abc123")
    assert r == {"ok": True, "reasons": [], "warnings": []}


def test_unreachable_server_fails_with_one_clear_reason():
    r = dv.judge(None, None, [], None)
    assert not r["ok"] and "not reachable" in r["reasons"][0]


def test_page_loaded_is_not_enough_when_the_mount_is_empty():
    # The white screen: navigation finished, zero failures, nothing rendered.
    r = dv.judge(HEALTH, _dom(mountChildren=0), [], NO_CRASH)
    assert not r["ok"]
    assert any("white screen" in x for x in r["reasons"])


def test_zero_height_render_fails():
    r = dv.judge(HEALTH, _dom(mountFirstChildHeight=0), [], NO_CRASH)
    assert any("zero-height" in x for x in r["reasons"])


def test_counted_failures_fail_and_are_quoted():
    fails = [{"seq": 3, "kind": "http", "message": "HTTP 404 (subresource)", "source": "https://appassets.androidplatform.net/assets/x.js"}]
    r = dv.judge({**HEALTH, "pageFailures": 1}, DOM, fails, NO_CRASH)
    assert not r["ok"]
    assert any("assets/x.js" in x for x in r["reasons"])


def test_wrong_package_on_the_port_fails():
    r = dv.judge(HEALTH, DOM, [], NO_CRASH, expect_pkg="com.other")
    assert any("another app holds the port" in x for x in r["reasons"])


def test_stale_install_fails_but_unstamped_build_only_warns():
    assert not dv.judge(HEALTH, DOM, [], NO_CRASH, expect_sha="fff")["ok"]
    r = dv.judge({**HEALTH, "sha": "local"}, DOM, [], NO_CRASH, expect_sha="fff")
    assert r["ok"] and any("sha=local" in w for w in r["warnings"])


def test_crash_during_this_run_fails_an_older_one_warns():
    crash = {"present": True, "modifiedMs": 2000, "text": "versionName=1\ngitSha=a\n\njava.lang.IllegalStateException: boom\n"}
    now = dv.judge(HEALTH, DOM, [], crash, launched_ms=1000)
    assert not now["ok"] and "IllegalStateException" in now["reasons"][0]
    old = dv.judge(HEALTH, DOM, [], crash, launched_ms=5000)
    assert old["ok"] and "earlier run" in old["warnings"][0]


def test_page_that_did_not_answer_the_probe_fails():
    r = dv.judge(HEALTH, {"host": DOM["host"], "page": None}, [], NO_CRASH)
    assert any("did not answer" in x for x in r["reasons"])


def test_detached_webview_fails():
    r = dv.judge(HEALTH, {"host": {"attached": False}, "page": DOM["page"]}, [], NO_CRASH)
    assert any("not attached" in x for x in r["reasons"])


def test_without_a_mount_element_body_is_judged_and_it_says_so():
    ok = dv.judge(HEALTH, _dom(mountPresent=False, mountChildren=-1), [], NO_CRASH)
    assert ok["ok"] and any("judged on <body>" in w for w in ok["warnings"])
    blank = dv.judge(HEALTH, _dom(mountPresent=False, bodyChildren=0), [], NO_CRASH)
    assert any("blank" in x for x in blank["reasons"])


def test_cli_exit_codes_and_missing_files(tmp_path):
    h = tmp_path / "h.json"; h.write_text(json.dumps(HEALTH))
    d = tmp_path / "d.json"; d.write_text(json.dumps(DOM))
    f = tmp_path / "f.json"; f.write_text("[]")
    c = tmp_path / "c.json"; c.write_text(json.dumps(NO_CRASH))
    cli = [sys.executable, str(RUNTIME_BIN / "device_verdict.py"), "judge"]
    good = subprocess.run(cli + ["--health", str(h), "--dom", str(d), "--failures", str(f), "--crash", str(c)],
                          capture_output=True, text=True)
    assert good.returncode == 0 and json.loads(good.stdout)["ok"]
    # An empty file (curl got nothing) is "no response", never a crash of the judge.
    empty = tmp_path / "empty.json"; empty.write_text("")
    bad = subprocess.run(cli + ["--health", str(empty), "--dom", str(d)], capture_output=True, text=True)
    assert bad.returncode == 1 and "not reachable" in bad.stdout


def test_bundle_scripts_reads_hashed_names():
    html = '<script type="module" crossorigin src="/assets/index-ChNv93mm.js"></script><script src="./b.js?v=2"></script><script>inline()</script>'
    assert dv.bundle_scripts(html) == ["b.js", "index-ChNv93mm.js"]


def test_stale_install_is_caught_by_bundle_hash_when_sha_is_local():
    # The real case: sha=local on both builds, different content-hashed bundles.
    dom = _dom(scripts=["https://appassets.androidplatform.net/assets/index-Cm8fn7Mn.js [module]"])
    stale = dv.judge({**HEALTH, "sha": "local"}, dom, [], NO_CRASH, expect_scripts=["index-ChNv93mm.js"])
    assert not stale["ok"] and any("different bundle build" in x for x in stale["reasons"])
    fresh = dv.judge({**HEALTH, "sha": "local"}, dom, [], NO_CRASH, expect_scripts=["index-Cm8fn7Mn.js"])
    assert fresh["ok"]
