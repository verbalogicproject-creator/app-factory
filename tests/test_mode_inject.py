"""mode_inject: carries android-dev mode, and must never break a turn.

The load-bearing property is the last one: on UserPromptSubmit an exit code of 2 erases
the user's prompt. Every failure path here must still exit 0.
"""
import json
import os
import subprocess
import sys

import pytest

from tests.conftest import HOOKS, PLUGIN, load_module

SCRIPT = HOOKS / "mode_inject.py"
mode_inject = load_module("mode_inject", SCRIPT)


def run(payload: dict, env_extra: dict | None = None) -> tuple[int, str, str]:
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN)
    env.update(env_extra or {})
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def enable(tmp_path, value: str = "true"):
    d = tmp_path / ".claude"
    d.mkdir(parents=True, exist_ok=True)
    (d / "appfactory.local.md").write_text(
        f"---\nmode: android-dev\nenabled: {value}\nactivated: 2026-09-13T00:00:00Z\n---\n\nbody\n"
    )
    return str(tmp_path)


# ── off is the default, and must cost nothing ─────────────────────────────────

def test_no_state_file_injects_nothing(tmp_path):
    rc, out, _ = run({"hook_event_name": "UserPromptSubmit", "cwd": str(tmp_path)})
    assert rc == 0 and out.strip() == ""


def test_enabled_false_injects_nothing(tmp_path):
    cwd = enable(tmp_path, "false")
    rc, out, _ = run({"hook_event_name": "UserPromptSubmit", "cwd": cwd})
    assert rc == 0 and out.strip() == ""


@pytest.mark.parametrize("value", ["true", "True", "yes", "on"])
def test_truthy_values_enable(tmp_path, value):
    cwd = enable(tmp_path, value)
    assert mode_inject.mode_enabled(cwd) is True


@pytest.mark.parametrize("value", ["false", "no", "off", "maybe", ""])
def test_non_truthy_values_do_not_enable(tmp_path, value):
    cwd = enable(tmp_path, value)
    assert mode_inject.mode_enabled(cwd) is False


# ── on: the right payload for the right event ─────────────────────────────────

def test_user_prompt_submit_injects_the_short_anchor(tmp_path):
    cwd = enable(tmp_path)
    rc, out, _ = run({"hook_event_name": "UserPromptSubmit", "cwd": cwd})
    assert rc == 0
    doc = json.loads(out)
    ctx = doc["hookSpecificOutput"]["additionalContext"]
    assert doc["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "android-dev mode is ON" in ctx
    # Cheap enough to pay every single turn.
    assert len(ctx) < 800, "the per-turn anchor must stay small"
    assert "systemMessage" not in doc


def test_session_start_injects_the_full_doctrine_and_tells_the_user(tmp_path):
    cwd = enable(tmp_path)
    rc, out, _ = run({"hook_event_name": "SessionStart", "cwd": cwd})
    assert rc == 0
    doc = json.loads(out)
    ctx = doc["hookSpecificOutput"]["additionalContext"]
    assert doc["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "Never run bare" in ctx and "aapt2 2.19" in ctx
    assert len(ctx) > 2000, "session start carries the real doctrine"
    assert doc["systemMessage"] == "android-dev mode: ON (appfactory pipeline)"


def test_doctrine_is_under_the_injection_cap():
    text = mode_inject.doctrine(str(PLUGIN))
    assert len(text) <= mode_inject.MAX_CONTEXT_CHARS


def test_oversized_doctrine_is_truncated_not_dropped(tmp_path, monkeypatch):
    big = tmp_path / "plugin" / "references"
    big.mkdir(parents=True)
    (big / "android-mode.md").write_text("x" * (mode_inject.MAX_CONTEXT_CHARS + 500))
    text = mode_inject.doctrine(str(tmp_path / "plugin"))
    assert len(text) <= mode_inject.MAX_CONTEXT_CHARS + 200
    assert "truncated" in text


def test_missing_doctrine_file_falls_back_to_the_anchor(tmp_path):
    assert mode_inject.doctrine(str(tmp_path)) == mode_inject.ANCHOR


# ── a mode must never break a turn ────────────────────────────────────────────

def test_malformed_stdin_exits_zero():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)], input="not json", capture_output=True, text=True, timeout=10
    )
    assert proc.returncode == 0


def test_empty_stdin_exits_zero():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)], input="", capture_output=True, text=True, timeout=10
    )
    assert proc.returncode == 0


def test_unreadable_state_file_exits_zero(tmp_path):
    d = tmp_path / ".claude"
    d.mkdir()
    (d / "appfactory.local.md").mkdir()  # a directory where a file is expected
    rc, _, _ = run({"hook_event_name": "UserPromptSubmit", "cwd": str(tmp_path)})
    assert rc == 0


def test_missing_cwd_exits_zero():
    rc, _, _ = run({"hook_event_name": "UserPromptSubmit"})
    assert rc == 0


def test_unknown_event_still_emits_a_valid_envelope(tmp_path):
    cwd = enable(tmp_path)
    rc, out, _ = run({"hook_event_name": "SomethingNew", "cwd": cwd})
    assert rc == 0
    assert json.loads(out)["hookSpecificOutput"]["hookEventName"] == "SomethingNew"


def test_output_is_always_the_nested_object_never_a_bare_string(tmp_path):
    """A bare string works until the text happens to start with '{', at which point
    Claude Code parses it as JSON, fails, and drops the context silently."""
    cwd = enable(tmp_path)
    for event in ("UserPromptSubmit", "SessionStart"):
        _, out, _ = run({"hook_event_name": event, "cwd": cwd})
        doc = json.loads(out)
        assert set(doc["hookSpecificOutput"]) >= {"hookEventName", "additionalContext"}
