"""statusline/android_mode.sh -- the mode indicator.

Two properties are load-bearing, and neither is obvious from reading the script:

1. Claude Code discards the ENTIRE status line unless the command exits 0
   (cli.js 2.1.112, AJ7: `if (w.status === 0)`). A crash here does not show an
   error -- it silently removes the line, which looks exactly like the mode
   being off. So every path must exit 0.
2. `--fragment DIR` must not read stdin. The composing wrapper has already
   parsed the payload, and a second python3 startup costs ~110ms per render
   on this device.
"""
from __future__ import annotations

import subprocess

import pytest

from tests.conftest import PLUGIN

SCRIPT = PLUGIN / "statusline" / "android_mode.sh"


def run(args: list[str], stdin: str = "") -> tuple[int, str]:
    proc = subprocess.run(
        ["bash", str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return proc.returncode, proc.stdout


def project(tmp_path, enabled: str | None):
    """A project dir, optionally carrying the mode state file."""
    if enabled is not None:
        d = tmp_path / ".claude"
        d.mkdir(parents=True, exist_ok=True)
        (d / "appfactory.local.md").write_text(
            f"---\nmode: android-dev\nenabled: {enabled}\n---\n\nbody\n"
        )
    return str(tmp_path)


def payload(cwd: str) -> str:
    return '{"workspace": {"current_dir": "%s"}}' % cwd


# ── the script exists and is executable ───────────────────────────────────────

def test_script_is_executable():
    assert SCRIPT.exists()
    assert SCRIPT.stat().st_mode & 0o111, "statusLine commands are exec'd directly"


def test_script_is_valid_bash():
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0


# ── off is the default and must be silent ─────────────────────────────────────

def test_no_state_file_shows_no_indicator(tmp_path):
    rc, out = run(["--fragment", project(tmp_path, None)])
    assert rc == 0 and out == ""


@pytest.mark.parametrize("value", ["false", "no", "off", "maybe", ""])
def test_non_truthy_shows_no_indicator(tmp_path, value):
    rc, out = run(["--fragment", project(tmp_path, value)])
    assert rc == 0 and out == ""


# ── on ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", ["true", "True", "TRUE", "yes", "on"])
def test_truthy_shows_the_indicator(tmp_path, value):
    rc, out = run(["--fragment", project(tmp_path, value)])
    assert rc == 0
    assert "android-dev" in out
    assert "\033[32m" in out, "the dot is green so the mode reads at a glance"


def test_fragment_omits_the_directory(tmp_path):
    """Composed into a wrapper that prints the directory itself; printing it here
    too would duplicate it."""
    cwd = project(tmp_path, "true")
    _, out = run(["--fragment", cwd])
    assert tmp_path.name not in out


def test_standalone_appends_the_directory(tmp_path):
    """Standalone REPLACES the default footer, so a bare indicator would lose the
    only location cue the user had."""
    cwd = project(tmp_path, "true")
    rc, out = run([cwd])
    assert rc == 0
    assert "android-dev" in out and out.endswith(tmp_path.name)


def test_standalone_off_prints_only_the_directory(tmp_path):
    rc, out = run([project(tmp_path, None)])
    assert rc == 0 and out == tmp_path.name


# ── the composition contract ──────────────────────────────────────────────────

def test_fragment_with_dir_ignores_stdin(tmp_path):
    """If it still parsed stdin, this garbage would either crash it or override
    the directory it was handed."""
    cwd = project(tmp_path, "true")
    rc, out = run(["--fragment", cwd], stdin="}{ not json " * 500)
    assert rc == 0 and "android-dev" in out


def test_stdin_is_read_when_no_dir_is_given(tmp_path):
    cwd = project(tmp_path, "true")
    rc, out = run([], stdin=payload(cwd))
    assert rc == 0 and "android-dev" in out


def test_flat_cwd_key_is_accepted_as_a_fallback(tmp_path):
    cwd = project(tmp_path, "true")
    rc, out = run([], stdin='{"cwd": "%s"}' % cwd)
    assert rc == 0 and "android-dev" in out


# ── never blank the line ──────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "stdin", ["", "not json", "[1,2,3]", "null", '{"workspace": null}', '{"workspace": {}}']
)
def test_degenerate_stdin_still_exits_zero(stdin):
    rc, out = run([], stdin=stdin)
    assert rc == 0
    assert out != "", "a blank line is indistinguishable from the mode being off"


def test_state_file_that_is_a_directory_exits_zero(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "appfactory.local.md").mkdir()
    rc, _ = run(["--fragment", str(tmp_path)])
    assert rc == 0


def test_unreadable_state_file_exits_zero(tmp_path):
    cwd = project(tmp_path, "true")
    (tmp_path / ".claude" / "appfactory.local.md").chmod(0o000)
    try:
        rc, _ = run(["--fragment", cwd])
        assert rc == 0
    finally:
        (tmp_path / ".claude" / "appfactory.local.md").chmod(0o644)


def test_enabled_must_be_its_own_line_not_a_substring(tmp_path):
    """`# enabled: true` in prose must not switch the mode on."""
    d = tmp_path / ".claude"
    d.mkdir(parents=True)
    (d / "appfactory.local.md").write_text(
        "---\nmode: android-dev\nenabled: false\n---\n\nTo start, set enabled: true here.\n"
    )
    rc, out = run(["--fragment", str(tmp_path)])
    assert rc == 0 and out == ""
