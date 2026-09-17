"""Tests for runtime/bin/ladder.py stage ordering."""
from __future__ import annotations

from tests.conftest import RUNTIME_BIN, load_module

ladder = load_module("ladder", RUNTIME_BIN / "ladder.py")


def test_device_stage_pulls_in_the_debug_build_and_follows_instrumented():
    assert ladder.expand(["device"]) == ["debug", "device"]
    assert ladder.STAGES.index("instrumented") < ladder.STAGES.index("device") < ladder.STAGES.index("release")


def test_every_stage_has_a_runner_in_local_build():
    # A stage the ladder knows but the shell cannot run would fail as "command not found".
    sh = (RUNTIME_BIN.parent / "scripts" / "local-build.sh").read_text()
    for st in ladder.STAGES:
        assert f"run_{st.replace('-', '_')}()" in sh, st
