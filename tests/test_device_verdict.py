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


# ---------------------------------------------------------------------------
# App-declared checks
# ---------------------------------------------------------------------------
def _obs(**kw):
    base = {"observed_at": 1000, "context_time": 1.0, "level_db": None, "voice_detail": []}
    return {**base, **kw}


C4_ON = _obs(level_db=-27.0, signal_hz=257.8, voice_detail=[{"id": "0", "frequency_hz": 261.6, "amp": 0.24}])
C4_OFF = _obs(level_db=-59.0, voice_detail=[{"id": "0", "frequency_hz": 261.6, "amp": 0}])


def test_a_sounding_note_at_the_right_pitch_passes():
    # Numbers from the phone, 2026-09-17: noteOn C4 -> signal_hz 257.8, amp 0.24.
    assert dv.expectation_reasons({"status": "applied", "signal_hz": [261.6, 0.1], "voice_amp_above": 0.05},
                                  {"status": "applied"}, [C4_ON]) == []


def test_wrong_pitch_and_silence_fail_differently():
    wrong = dv.expectation_reasons({"signal_hz": [261.6, 0.1]}, None, [_obs(signal_hz=392.0)])
    assert "392 Hz" in wrong[0]
    silent = dv.expectation_reasons({"signal_hz": [261.6, 0.1]}, None, [_obs()])
    assert "no signal_hz" in silent[0]


def test_a_stuck_voice_fails_and_a_released_one_passes():
    stuck = _obs(voice_detail=[{"id": "0", "frequency_hz": 392.0, "amp": 0.32}])
    assert "stuck note" in dv.expectation_reasons({"voices_silent": True}, None, [stuck])[0]
    assert dv.expectation_reasons({"voices_silent": True}, None, [C4_OFF]) == []


def test_applied_is_not_an_effect():
    # The reply says applied, the observation says nothing started: that is a failure.
    r = dv.expectation_reasons({"status": "applied", "voice_amp_above": 0.05}, {"status": "applied"}, [C4_OFF])
    assert any("did not start" in x for x in r)


def test_expectations_the_observation_cannot_answer_fail_rather_than_pass():
    bare = {"observed_at": 1, "level_db": -20}
    r = dv.expectation_reasons({"voices_silent": True, "clock_rate_min": 0.9}, None, [bare])
    assert any("no voice_detail" in x for x in r)
    assert any("cannot measure the audio clock" in x for x in r)
    assert dv.expectation_reasons({"level_db_below": -40}, None, []) == ["no observation to judge (is /__sag/observe wired?)"]


def test_clock_rate_detects_a_render_thread_falling_behind():
    keeping_up = [_obs(observed_at=0, context_time=10.0), _obs(observed_at=2000, context_time=11.98)]
    behind = [_obs(observed_at=0, context_time=10.0), _obs(observed_at=2000, context_time=11.0)]
    assert dv.expectation_reasons({"clock_rate_min": 0.9}, None, keeping_up) == []
    assert "0.50x" in dv.expectation_reasons({"clock_rate_min": 0.9}, None, behind)[0]


def test_level_null_counts_as_silent():
    assert dv.expectation_reasons({"level_db_below": -40}, None, [_obs(level_db=None)]) == []
    assert dv.expectation_reasons({"level_db_below": -40}, None, [_obs(level_db=-25.0)])


def test_run_checks_sequences_io_and_reports_each_step():
    log = []
    state = {"obs": [C4_ON]}

    def post(cmd):
        log.append(("post", cmd["type"]))
        if cmd["type"] == "noteOff":
            state["obs"] = [C4_OFF]
        return {"status": "applied"}

    steps = [
        {"name": "on", "command": {"type": "noteOn", "note": "C4"}, "wait_ms": 10, "expect": {"voice_amp_above": 0.05}},
        {"name": "hidden", "background": True, "wait_ms": 10, "expect": {"voices_silent": True}},
        {"name": "back", "foreground": True, "command": {"type": "noteOff", "note": "C4"}, "wait_ms": 10,
         "expect": {"voices_silent": True}},
    ]
    r = dv.run_checks(steps, post, lambda n: state["obs"], lambda: log.append("bg"), lambda: log.append("fg"),
                      lambda s: None)
    assert [s["ok"] for s in r["steps"]] == [True, False, True]
    assert "stuck note" in r["steps"][1]["reasons"][0]
    assert not r["ok"]
    assert log == [("post", "noteOn"), "bg", ("post", "noteOff"), "fg"]


def test_a_step_that_raises_fails_and_an_empty_check_list_is_not_a_pass():
    def boom(cmd):
        raise ConnectionRefusedError("server gone")
    r = dv.run_checks([{"command": {"type": "noteOn"}, "expect": {}}], boom, lambda n: [], lambda: None, lambda: None,
                      lambda s: None)
    assert not r["ok"] and "ConnectionRefusedError" in r["steps"][0]["reasons"][0]
    assert not dv.run_checks([], boom, lambda n: [], lambda: None, lambda: None, lambda s: None)["ok"]


def test_checks_cli_keeps_its_subcommand_and_tool_flags_apart(tmp_path):
    # --cmd once shared argparse's dest with the subcommand name and silently replaced it.
    f = tmp_path / "c.json"; f.write_text('{"steps": []}')
    proc = subprocess.run([sys.executable, str(RUNTIME_BIN / "device_verdict.py"), "checks", "--file", str(f),
                           "--pkg", "x", "--cmd", "/nonexistent", "--base", "http://127.0.0.1:9"],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 1 and json.loads(proc.stdout)["steps"] == []
