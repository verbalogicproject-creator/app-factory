"""Tests for runtime/bin/scaffold.py -- the walking-skeleton generator."""
from __future__ import annotations

import filecmp
import os
import py_compile
import re
import shutil
import stat
import subprocess
import sys

import pytest

from tests.conftest import ROOT, RUNTIME_BIN, load_module

scaffold = load_module("scaffold", RUNTIME_BIN / "scaffold.py")
contract = load_module("contract", RUNTIME_BIN / "contract.py")

TEMPLATES = scaffold.TEMPLATES
WEB_DIR = ROOT / "tests" / "data" / "web"


def _run_main(argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["scaffold.py", *argv])
    return scaffold.main()


# ---------------------------------------------------------------------------
# substitutions(): pure logic, no filesystem
# ---------------------------------------------------------------------------
def test_substitutions_class_name_from_app_name():
    subs = scaffold.substitutions("com.example.myapp", "My Cool App")
    assert subs["{{APP_CLASS}}"] == "MyCoolApp"


def test_substitutions_class_name_falls_back_to_app_when_unwordy():
    subs = scaffold.substitutions("com.example.myapp", "!!!")
    assert subs["{{APP_CLASS}}"] == "App"


def test_substitutions_slug_is_lowercase_hyphenated():
    subs = scaffold.substitutions("com.example.myapp", "My Cool App!")
    assert subs["{{APP_SLUG}}"] == "my-cool-app"


def test_substitutions_upper():
    subs = scaffold.substitutions("com.example.myapp", "My App")
    assert subs["{{APP_NAME_UPPER}}"] == "MY APP"


def test_substitutions_application_id_passthrough():
    subs = scaffold.substitutions("com.example.myapp", "My App")
    assert subs["{{APPLICATION_ID}}"] == "com.example.myapp"


# ---------------------------------------------------------------------------
# argument validation: SystemExit before anything is written
# ---------------------------------------------------------------------------
def test_invalid_application_id_exits(tmp_path, monkeypatch):
    with pytest.raises(SystemExit):
        _run_main(
            [str(tmp_path / "out"), "--application-id", "NotAValidId", "--app-name", "X"],
            monkeypatch,
        )


def test_single_segment_application_id_exits(tmp_path, monkeypatch):
    with pytest.raises(SystemExit):
        _run_main(
            [str(tmp_path / "out"), "--application-id", "example", "--app-name", "X"],
            monkeypatch,
        )


def test_min_sdk_below_26_exits(tmp_path, monkeypatch):
    with pytest.raises(SystemExit):
        _run_main(
            [
                str(tmp_path / "out"),
                "--application-id", "com.example.x",
                "--app-name", "X",
                "--min-sdk", "25",
            ],
            monkeypatch,
        )


def test_nonempty_target_without_force_exits(tmp_path, monkeypatch):
    target = tmp_path / "out"
    target.mkdir()
    (target / "existing-file").write_text("already here")
    with pytest.raises(SystemExit):
        _run_main(
            [str(target), "--application-id", "com.example.x", "--app-name", "X"],
            monkeypatch,
        )


def test_nonempty_target_with_force_succeeds(tmp_path, monkeypatch):
    target = tmp_path / "out"
    target.mkdir()
    (target / "existing-file").write_text("already here")
    rc = _run_main(
        [
            str(target), "--application-id", "com.example.x", "--app-name", "X",
            "--force",
        ],
        monkeypatch,
    )
    assert rc == 0


# ---------------------------------------------------------------------------
# happy path: full generation into tmp_path
# ---------------------------------------------------------------------------
@pytest.fixture
def scaffolded(tmp_path, monkeypatch):
    target = tmp_path / "demo"
    rc = _run_main(
        [
            str(target),
            "--application-id", "com.example.demoapp",
            "--app-name", "Demo App",
        ],
        monkeypatch,
    )
    assert rc == 0
    return target


def test_no_unrendered_placeholders_outside_fixtures(scaffolded):
    # Mirrors preflight check 110: a placeholder token is {{UPPER_SNAKE}}, not
    # preceded by '$' (GitHub Actions' ${{ ... }} shares the braces but is a
    # different syntax). scripts/preflight/ legitimately quotes placeholders in
    # its own documentation/checks, and its fixtures/ trees are deliberately
    # broken samples -- both excluded, exactly as check 110 excludes them.
    placeholder = re.compile(r'\{\{[A-Z][A-Z0-9_]*\}\}')
    offenders = []
    for root, _dirs, files in os.walk(scaffolded):
        rel_root = os.path.relpath(root, scaffolded).replace(os.sep, "/")
        if rel_root.startswith("scripts/preflight"):
            continue
        for f in files:
            path = os.path.join(root, f)
            try:
                lines = open(path, encoding="utf-8").readlines()
            except (UnicodeDecodeError, IsADirectoryError):
                continue
            for lineno, line in enumerate(lines, 1):
                for m in placeholder.finditer(line):
                    if line[max(0, m.start() - 1):m.start()] == "$":
                        continue
                    offenders.append(f"{os.path.relpath(path, scaffolded)}:{lineno} {m.group()}")
    assert offenders == []


def test_gradlew_is_executable(scaffolded):
    mode = os.stat(scaffolded / "gradlew").st_mode
    assert mode & stat.S_IXUSR


def test_gradlew_bat_byte_identical_to_template(scaffolded):
    template = os.path.join(TEMPLATES, "gradle", "gradlew.bat")
    generated = scaffolded / "gradlew.bat"
    assert filecmp.cmp(template, generated, shallow=False)


def test_gradle_wrapper_jar_byte_identical_to_template(scaffolded):
    template = os.path.join(TEMPLATES, "gradle", "gradle-wrapper.jar")
    generated = scaffolded / "gradle" / "wrapper" / "gradle-wrapper.jar"
    assert filecmp.cmp(template, generated, shallow=False)


def test_ui_files_nested_under_package_path(scaffolded):
    pkg_path = "com/example/demoapp"
    home_screen = scaffolded / "app/src/main/java" / pkg_path / "ui" / "HomeScreen.kt"
    theme = scaffolded / "app/src/main/java" / pkg_path / "ui/theme" / "Theme.kt"
    assert home_screen.is_file()
    assert theme.is_file()


def test_workflows_contain_application_id(scaffolded):
    wf_dir = scaffolded / ".github" / "workflows"
    assert wf_dir.is_dir()
    found = False
    for wf in wf_dir.iterdir():
        if "com.example.demoapp" in wf.read_text(encoding="utf-8"):
            found = True
    assert found


def test_no_pycache_vendored(tmp_path, monkeypatch):
    # Compile a real runtime/bin source file to produce a genuine __pycache__
    # directory under the source tree scaffold.py vendors from, run a scaffold,
    # and assert none of it was copied into the generated project. The
    # __pycache__ is removed afterward regardless of outcome: it is build
    # output of this repo's own tooling, not something the repo should carry.
    pycache_dir = RUNTIME_BIN / "__pycache__"
    pre_existing = pycache_dir.is_dir()
    try:
        py_compile.compile(str(RUNTIME_BIN / "scaffold.py"), doraise=True)
        assert pycache_dir.is_dir(), "py_compile did not create __pycache__ as expected"

        target = tmp_path / "demo"
        rc = _run_main(
            [str(target), "--application-id", "com.example.pycachetest", "--app-name", "X"],
            monkeypatch,
        )
        assert rc == 0

        offenders = [
            p for p in target.rglob("__pycache__")
        ] + [p for p in target.rglob("*.pyc")]
        assert offenders == [], f"__pycache__/.pyc vendored into scaffold output: {offenders}"
    finally:
        if not pre_existing and pycache_dir.is_dir():
            shutil.rmtree(pycache_dir)


@pytest.mark.slow
def test_preflight_passes_on_scaffolded_project(scaffolded):
    preflight = scaffolded / "scripts" / "preflight.sh"
    assert preflight.is_file()
    r = subprocess.run(
        ["bash", str(preflight), str(scaffolded)],
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# --kind web-shell
# ---------------------------------------------------------------------------
@pytest.fixture
def web_shell_scaffolded(tmp_path, monkeypatch):
    target = tmp_path / "webshell-demo"
    rc = _run_main(
        [
            str(target),
            "--application-id", "com.example.webshelldemo",
            "--app-name", "Web Shell Demo",
            "--kind", "web-shell",
            "--web-dir", str(WEB_DIR),
            "--deeplink-scheme", "synth",
        ],
        monkeypatch,
    )
    assert rc == 0
    return target


def test_web_shell_requires_web_dir(tmp_path, monkeypatch):
    with pytest.raises(SystemExit):
        _run_main(
            [
                str(tmp_path / "out"),
                "--application-id", "com.example.nowebdir",
                "--app-name", "X",
                "--kind", "web-shell",
            ],
            monkeypatch,
        )


def test_web_shell_dies_on_a_web_dir_with_no_index_html(tmp_path, monkeypatch):
    empty_dir = tmp_path / "not-a-bundle"
    empty_dir.mkdir()
    (empty_dir / "app.js").write_text("// no index.html here")
    with pytest.raises(SystemExit):
        _run_main(
            [
                str(tmp_path / "out"),
                "--application-id", "com.example.badwebdir",
                "--app-name", "X",
                "--kind", "web-shell",
                "--web-dir", str(empty_dir),
            ],
            monkeypatch,
        )


def test_web_shell_copies_the_bundle_into_assets(web_shell_scaffolded):
    """The fixture bundle is shaped like a bundler's output -- hashed files under an
    assets/ subdirectory, referenced by absolute path -- so this also covers the copy
    preserving nesting, which a flat bundle would not have caught."""
    assets = web_shell_scaffolded / "app/src/main/assets/web"
    assert (assets / "index.html").is_file()
    assert (assets / "assets" / "app-D4f8a1c2.js").is_file()
    assert (assets / "assets" / "style-B7e2d9f0.css").is_file()


def test_web_shell_bundle_keeps_its_absolute_asset_paths(web_shell_scaffolded):
    """Absolute /assets/... is what a default `vite build` emits and what the root-mounted
    WebViewAssetLoader handler exists to serve. If the fixture ever drifts back to
    relative paths, the instrumented test silently stops covering the white-screen bug."""
    index = (web_shell_scaffolded / "app/src/main/assets/web/index.html").read_text(encoding="utf-8")
    assert 'src="/assets/app-D4f8a1c2.js"' in index
    assert 'href="/assets/style-B7e2d9f0.css"' in index


def test_web_shell_manifest_has_deeplink_scheme_and_network_wiring(web_shell_scaffolded):
    manifest = (web_shell_scaffolded / "app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    assert 'android:scheme="synth"' in manifest
    assert "android.permission.INTERNET" in manifest
    assert 'android:networkSecurityConfig="@xml/network_security_config"' in manifest
    assert (web_shell_scaffolded / "app/src/main/res/xml/network_security_config.xml").is_file()


def test_web_shell_overlay_files_are_nested_under_the_package(web_shell_scaffolded):
    pkg_path = "com/example/webshelldemo"
    java = web_shell_scaffolded / "app/src/main/java" / pkg_path
    assert (java / "web" / "WebShellScreen.kt").is_file()
    assert (java / "bridge" / "NativeBridge.kt").is_file()
    assert (java / "bridge" / "CommandServer.kt").is_file()
    assert (java / "bridge" / "PendingReplies.kt").is_file()
    assert (java / "service" / "ShellForegroundService.kt").is_file()


def test_web_shell_no_unrendered_placeholders(web_shell_scaffolded):
    placeholder = re.compile(r'\{\{[A-Z][A-Z0-9_]*\}\}')
    offenders = []
    for root, _dirs, files in os.walk(web_shell_scaffolded):
        rel_root = os.path.relpath(root, web_shell_scaffolded).replace(os.sep, "/")
        if rel_root.startswith("scripts/preflight"):
            continue
        for f in files:
            path = os.path.join(root, f)
            try:
                lines = open(path, encoding="utf-8").readlines()
            except (UnicodeDecodeError, IsADirectoryError):
                continue
            for lineno, line in enumerate(lines, 1):
                for m in placeholder.finditer(line):
                    if line[max(0, m.start() - 1):m.start()] == "$":
                        continue
                    offenders.append(f"{os.path.relpath(path, web_shell_scaffolded)}:{lineno} {m.group()}")
    assert offenders == []


@pytest.mark.slow
def test_preflight_passes_on_web_shell_scaffolded_project(web_shell_scaffolded):
    preflight = web_shell_scaffolded / "scripts" / "preflight.sh"
    assert preflight.is_file()
    r = subprocess.run(
        ["bash", str(preflight), str(web_shell_scaffolded)],
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_kind_compose_output_only_differs_by_the_empty_web_shell_substitutions(tmp_path, monkeypatch):
    """--kind compose must render byte-identical to omitting --kind entirely,
    except where a web-shell-only placeholder resolves to an empty string."""
    target_default = tmp_path / "default"
    target_explicit = tmp_path / "explicit-compose"
    for target in (target_default, target_explicit):
        argv = [
            str(target),
            "--application-id", "com.example.samesame",
            "--app-name", "Same Same",
        ]
        if target is target_explicit:
            argv += ["--kind", "compose"]
        assert _run_main(argv, monkeypatch) == 0

    mismatches = []
    for root, _dirs, files in os.walk(target_default):
        for f in files:
            a = os.path.join(root, f)
            rel = os.path.relpath(a, target_default)
            b = os.path.join(target_explicit, rel)
            if not filecmp.cmp(a, b, shallow=False):
                mismatches.append(rel)
    assert mismatches == []


# ---------------------------------------------------------------------------
# --contract
# ---------------------------------------------------------------------------
def test_contract_fills_kind_and_web_dir(tmp_path, monkeypatch):
    contract_dir = tmp_path / "contract-out"
    rc = contract.main([
        "init",
        "--out", str(contract_dir),
        "--application-id", "com.example.fromcontract",
        "--app-name", "From Contract",
        "--kind", "web-shell",
        "--web-dir", str(WEB_DIR),
        "--deeplink-scheme", "synth",
        "--target-sdk", "36",
        "--date", "2026-08-15",
    ])
    assert rc == 0

    target = tmp_path / "out"
    rc = _run_main(
        [str(target), "--contract", str(contract_dir)],
        monkeypatch,
    )
    assert rc == 0
    assert (target / "app/src/main/assets/web/index.html").is_file()
    manifest = (target / "app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    assert 'android:scheme="synth"' in manifest
    assert (target / ".appfactory/contract/lattice.toml").is_file()


def test_explicit_flag_overrides_contract(tmp_path, monkeypatch):
    contract_dir = tmp_path / "contract-out"
    rc = contract.main([
        "init",
        "--out", str(contract_dir),
        "--application-id", "com.example.override",
        "--app-name", "Override Me",
        "--kind", "web-shell",
        "--web-dir", str(WEB_DIR),
        "--deeplink-scheme", "synth",
        "--target-sdk", "36",
        "--date", "2026-08-15",
    ])
    assert rc == 0

    target = tmp_path / "out"
    rc = _run_main(
        [str(target), "--contract", str(contract_dir), "--kind", "compose"],
        monkeypatch,
    )
    assert rc == 0
    assert not (target / "app/src/main/assets/web").exists()


def test_vendored_webdetect_finds_its_table(tmp_path, monkeypatch):
    # webdetect.py resolves its framework table as ../data/ from wherever it lives.
    # Vendoring bin/ without data/ shipped a tool that crashed on first use.
    target = tmp_path / "demo"
    rc = _run_main([str(target), "--application-id", "com.example.webdetect", "--app-name", "X"], monkeypatch)
    assert rc == 0
    web = tmp_path / "web"
    web.mkdir()
    (web / "package.json").write_text('{"devDependencies": {"vite": "5"}}')
    proc = subprocess.run(
        [sys.executable, str(target / ".appfactory/bin/webdetect.py"), "detect", str(web)],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert '"slug": "vite"' in proc.stdout
