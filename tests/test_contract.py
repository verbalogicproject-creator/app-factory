"""contract.py -- the decisions an app is built from, as a runner test."""
import json
import os
import subprocess
import sys
from datetime import date

import pytest

from tests.conftest import ROOT, load_module

CONTRACT = os.path.join(ROOT, "plugins/appfactory-core/runtime/bin/contract.py")
CHECK_140 = os.path.join(ROOT, "plugins/appfactory-core/runtime/scripts/preflight/checks/140-target-sdk-submittable.sh")


@pytest.fixture(scope="module")
def contract():
    return load_module("contract", CONTRACT)


def run(*args):
    return subprocess.run([sys.executable, CONTRACT, *args], capture_output=True, text=True)


# ── target-sdk floor is read from check 140, not carried ─────────────────────

def test_requirements_parsed_from_check_140(contract):
    rows = contract.parse_requirements(CHECK_140)
    assert rows and all(isinstance(d, date) and isinstance(n, int) for d, n in rows)
    assert rows == sorted(rows)


def test_floor_is_highest_in_force(contract):
    rows = [(date(2024, 8, 31), 34), (date(2025, 8, 31), 35), (date(2026, 8, 31), 36)]
    assert contract.target_sdk_floor(rows, date(2025, 1, 1)) == 34
    assert contract.target_sdk_floor(rows, date(2026, 9, 13)) == 36


def test_floor_takes_the_next_row_when_it_is_close(contract):
    rows = [(date(2025, 8, 31), 35), (date(2026, 8, 31), 36)]
    # 100 days before the 36 deadline: an app planned now is submitted later.
    assert contract.target_sdk_floor(rows, date(2026, 5, 23)) == 36
    # 200 days before: still 35.
    assert contract.target_sdk_floor(rows, date(2026, 2, 12)) == 35


def test_cli_floor_matches_library(contract):
    out = run("target-sdk-floor", "--date", "2026-09-13")
    assert out.returncode == 0
    assert int(out.stdout.strip()) == contract.target_sdk_floor(contract.parse_requirements(CHECK_140), date(2026, 9, 13))


# ── init / validate round trip ───────────────────────────────────────────────

def test_init_writes_three_files_and_validates(tmp_path):
    out = tmp_path / "contract"
    r = run("init", "--out", str(out), "--application-id", "com.example.demo", "--app-name", "Demo",
            "--date", "2026-09-13")
    assert r.returncode == 0, r.stderr
    for name in ("lattice.toml", "decisions.md", "UNVERIFIED.md"):
        assert (out / name).is_file()
    v = run("validate", str(out), "--date", "2026-09-13")
    assert v.returncode == 0, v.stdout + v.stderr
    show = json.loads(run("show", str(out)).stdout)
    assert show["app"]["application_id"] == "com.example.demo"
    assert show["app"]["target_sdk"] == 36
    assert show["app"]["kind"] == "compose"
    assert show["versions"]["agp"]  # the lattice was copied in
    # decisions.md names all three irreversible rows
    text = (out / "decisions.md").read_text()
    for label in ("applicationId", "signing certificate", "persisted schema version"):
        assert label in text


def test_unverified_lists_the_guesses(tmp_path):
    out = tmp_path / "c"
    run("init", "--out", str(out), "--application-id", "com.example.demo", "--app-name", "Demo",
        "--unverified", "the icon is final | drawn in a hurry | show it to the user")
    lines = [l for l in (out / "UNVERIFIED.md").read_text().splitlines() if l.startswith("- [ ]")]
    assert any("signing profile" in l for l in lines)
    assert any("Play package exists" in l for l in lines)
    assert any("the icon is final | drawn in a hurry | show it to the user" in l for l in lines)


def test_init_refuses_bad_application_id(tmp_path):
    r = run("init", "--out", str(tmp_path / "c"), "--application-id", "Demo", "--app-name", "Demo")
    assert r.returncode == 2 and "applicationId" in r.stderr


def test_init_refuses_min_sdk_below_26(tmp_path):
    r = run("init", "--out", str(tmp_path / "c"), "--application-id", "com.example.d", "--app-name", "D", "--min-sdk", "25")
    assert r.returncode == 2


def test_web_shell_needs_web_dir_with_index(tmp_path):
    r = run("init", "--out", str(tmp_path / "c"), "--application-id", "com.example.d", "--app-name", "D", "--kind", "web-shell")
    assert r.returncode == 2 and "web_dir" in r.stderr
    web = tmp_path / "dist"; web.mkdir()
    r = run("init", "--out", str(tmp_path / "c2"), "--application-id", "com.example.d", "--app-name", "D",
            "--kind", "web-shell", "--web-dir", str(web), "--deeplink-scheme", "synth")
    assert r.returncode == 2 and "index.html" in r.stderr
    (web / "index.html").write_text("<title>x</title>")
    r = run("init", "--out", str(tmp_path / "c3"), "--application-id", "com.example.d", "--app-name", "D",
            "--kind", "web-shell", "--web-dir", str(web), "--deeplink-scheme", "synth")
    assert r.returncode == 0, r.stderr


def test_validate_rejects_target_below_floor(tmp_path):
    out = tmp_path / "c"
    run("init", "--out", str(out), "--application-id", "com.example.d", "--app-name", "D", "--target-sdk", "36")
    toml = out / "lattice.toml"
    toml.write_text(toml.read_text().replace("target_sdk = 36", "target_sdk = 34"))
    v = run("validate", str(out), "--date", "2026-09-13")
    assert v.returncode == 1 and "below Play's floor" in v.stdout


def test_validate_rejects_malformed_unverified_line(tmp_path):
    out = tmp_path / "c"
    run("init", "--out", str(out), "--application-id", "com.example.d", "--app-name", "D")
    with open(out / "UNVERIFIED.md", "a") as f:
        f.write("- [ ] a guess with no why or how\n")
    v = run("validate", str(out))
    assert v.returncode == 1 and "UNVERIFIED.md" in v.stdout


def test_validate_rejects_bad_scheme(tmp_path, contract):
    out = tmp_path / "c"
    web = tmp_path / "dist"; web.mkdir(); (web / "index.html").write_text("x")
    run("init", "--out", str(out), "--application-id", "com.example.d", "--app-name", "D",
        "--kind", "web-shell", "--web-dir", str(web))
    toml = out / "lattice.toml"
    toml.write_text(toml.read_text().replace('deeplink_scheme = ""', 'deeplink_scheme = "Bad Scheme"'))
    assert contract.validate(str(out), date(2026, 9, 13), CHECK_140)
