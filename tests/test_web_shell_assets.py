"""The web-shell asset mount: three constants that must agree, and did not.

`vite build` emits `<script src="/assets/index-<hash>.js">`. The browser resolves that
against the ORIGIN, so what reaches WebViewAssetLoader is the path `/assets/index-<hash>.js`
-- no matter how deep the page itself was loaded from. While the handler was mounted at
`/assets/web/`, that request mapped to `android_asset/index-<hash>.js`, which does not
exist. The result was a blank page that passed all 21 preflight checks, the unit suite,
and the instrumented test, because none of them looked at whether the page's own assets
came back.

There is no Kotlin unit test here: the mapping needs a Context and Robolectric has no
ARM64 Linux runtime. But the mapping itself is three constants and a string concat, so
it is modelled here against the REAL values parsed out of the template, which catches the
drift that actually threatens it -- someone changing the mount without changing the
bundle directory, or vice versa.
"""
from __future__ import annotations

import re

import pytest

from tests.conftest import PLUGIN, ROOT, load_module

TEMPLATE = (
    PLUGIN
    / "runtime"
    / "templates"
    / "kinds"
    / "web-shell"
    / "app"
    / "src"
    / "main"
    / "java"
    / "web"
    / "WebShellScreen.kt"
)
SOURCE = TEMPLATE.read_text(encoding="utf-8")

#: Where scaffold.py copies --web-dir to, relative to app/src/main/assets/.
SCAFFOLD_ASSETS_SUBDIR = "web"


def mount_point() -> str:
    m = re.search(r'addPathHandler\(\s*"([^"]*)"', SOURCE)
    assert m, "no addPathHandler call found in the template"
    return m.group(1)


def bundle_dir() -> str:
    m = re.search(r'const val BUNDLE_DIR = "([^"]*)"', SOURCE)
    assert m, "no BUNDLE_DIR constant found in the template"
    return m.group(1)


def loaded_path() -> str:
    m = re.search(r'loadUrl\("https://appassets\.androidplatform\.net(/[^"]*)"\)', SOURCE)
    assert m, "no loadUrl of the asset-loader origin found in the template"
    return m.group(1)


def resolve(url_path: str) -> str:
    """Model WebViewAssetLoader: strip the registered prefix (PathMatcher.getSuffixPath),
    hand the remainder to the handler, which prepends the bundle dir before
    AssetsPathHandler opens it under android_asset/."""
    mount = mount_point()
    assert url_path.startswith(mount), f"{url_path} is not under the mount {mount}"
    return bundle_dir() + url_path[len(mount):]


# ── the constants agree ───────────────────────────────────────────────────────

def test_handler_is_mounted_at_the_root():
    """Anything deeper re-breaks absolute bundler paths."""
    assert mount_point() == "/"


def test_mount_point_is_valid_for_webviewassetloader():
    """PathMatcher throws IllegalArgumentException unless the path starts AND ends with
    a slash (verified against webkit-1.12.1.aar bytecode)."""
    mount = mount_point()
    assert mount.startswith("/") and mount.endswith("/")


def test_bundle_dir_matches_where_scaffold_puts_the_bundle():
    assert bundle_dir() == f"{SCAFFOLD_ASSETS_SUBDIR}/"


def test_the_page_is_loaded_from_the_bundle_root():
    assert loaded_path() == "/index.html"


# ── the mapping produces paths that exist ─────────────────────────────────────

def test_the_loaded_page_resolves_to_the_bundles_index():
    assert resolve(loaded_path()) == "web/index.html"


@pytest.mark.parametrize(
    "url_path, expected",
    [
        # What a default `vite build` emits -- the case that was broken.
        ("/assets/index-Cm8fn7Mn.js", "web/assets/index-Cm8fn7Mn.js"),
        ("/assets/index-Ce-D_BFC.css", "web/assets/index-Ce-D_BFC.css"),
        # Next/Astro-style absolute paths, and a plain root-level file.
        ("/_next/static/chunks/main.js", "web/_next/static/chunks/main.js"),
        ("/favicon.ico", "web/favicon.ico"),
        # A relative path resolved against /index.html lands here too.
        ("/sag-surface.json", "web/sag-surface.json"),
    ],
)
def test_absolute_bundler_paths_resolve_into_the_bundle(url_path, expected):
    assert resolve(url_path) == expected


def test_the_old_mount_would_have_missed_the_bundle():
    """The regression, stated as a test: under /assets/web/ the same request resolved
    outside the bundle entirely. Kept so the failure mode stays legible."""
    old_mount = "/assets/web/"
    url_path = "/assets/index-Cm8fn7Mn.js"
    assert not url_path.startswith(old_mount), (
        "the bundler's absolute path never matched the old mount's prefix beyond "
        "/assets/, so it resolved to android_asset/index-Cm8fn7Mn.js -- a 404"
    )


# ── the fixture bundle must keep reproducing the trap ─────────────────────────

def test_the_test_bundle_uses_absolute_paths_like_a_real_build():
    """A relative src= resolves under any mount, so a relative fixture would make the
    instrumented test green regardless of the bug. This is the guard on the guard."""
    index = (ROOT / "tests" / "data" / "web" / "index.html").read_text(encoding="utf-8")
    refs = re.findall(r'(?:src|href)="([^"]+)"', index)
    assert refs, "fixture index.html references no assets at all"
    assert all(r.startswith("/") for r in refs), f"fixture has non-absolute refs: {refs}"
    for ref in refs:
        assert (ROOT / "tests" / "data" / "web" / ref.lstrip("/")).is_file(), (
            f"{ref} is referenced but not present in the fixture"
        )


def test_the_instrumented_test_asserts_assets_loaded_not_just_the_title():
    """document.title comes out of the HTML and is correct even when every asset 404s."""
    test_src = (
        PLUGIN / "runtime" / "templates" / "kinds" / "web-shell"
        / "app" / "src" / "androidTest" / "java" / "WebShellTest.kt"
    ).read_text(encoding="utf-8")
    assert "__bundleAssetsResolved" in test_src, "nothing asserts the bundle's JS ran"
    assert "getComputedStyle" in test_src, "nothing asserts the bundle's CSS applied"


# ── the generated test must be able to pass for the project it is generated into ──

def test_scaffold_reads_the_title_from_the_bundle():
    """A generated project that ships a test asserting the FIXTURE's title fails on its
    first real run with nothing wrong with the app -- which teaches the reader to ignore
    the suite. G1c found exactly this: 'expected SAG Web Shell Test Bundle but was
    SAG-synth'."""
    scaffold = load_module("scaffold", PLUGIN / "runtime" / "bin" / "scaffold.py")
    assert scaffold.bundle_title(str(ROOT / "tests" / "data" / "web")) == "SAG Web Shell Test Bundle"


def test_bundle_title_survives_a_bundler_formatted_head(tmp_path):
    (tmp_path / "index.html").write_text(
        '<!doctype html>\n<html>\n  <head>\n    <title>\n      My  App\n    </title>\n', encoding="utf-8"
    )
    scaffold = load_module("scaffold", PLUGIN / "runtime" / "bin" / "scaffold.py")
    assert scaffold.bundle_title(str(tmp_path)) == "My App"


def test_bundle_title_is_empty_when_absent_so_the_app_name_is_used(tmp_path):
    (tmp_path / "index.html").write_text("<html><body>no title</body></html>", encoding="utf-8")
    scaffold = load_module("scaffold", PLUGIN / "runtime" / "bin" / "scaffold.py")
    assert scaffold.bundle_title(str(tmp_path)) == ""
    assert scaffold.substitutions("a.b", "Fallback Name", kind="web-shell")["{{WEB_TITLE}}"] == "Fallback Name"


def test_the_instrumented_test_carries_no_fixture_constants_outside_the_fixture_test():
    """The bundle-agnostic tests must not assert anything only the fixture provides."""
    src = (
        PLUGIN / "runtime" / "templates" / "kinds" / "web-shell"
        / "app" / "src" / "androidTest" / "java" / "WebShellTest.kt"
    ).read_text(encoding="utf-8")
    fixture_test = src[src.index("fun fixtureAbsoluteAssetPathsResolve"):]
    others = src[: src.index("fun fixtureAbsoluteAssetPathsResolve")]
    for marker in ("__bundleAssetsResolved", "rgb(0, 128, 64)"):
        assert marker in fixture_test, f"{marker} should still be covered for the fixture"
        assert marker not in others, f"{marker} is fixture-only and must not gate a real bundle"
    assert 'EXPECTED_TITLE = "{{WEB_TITLE}}"' in src, "the title must come from the bundle"
    assert "assumeTrue" in fixture_test, "the fixture test must skip, not fail, on a real bundle"


def test_the_layout_regression_is_asserted_on_device():
    """100vh resolving to 0 is what made a correct page invisible. Nothing cheaper than
    the instrumented rung can see it."""
    src = (
        PLUGIN / "runtime" / "templates" / "kinds" / "web-shell"
        / "app" / "src" / "androidTest" / "java" / "WebShellTest.kt"
    ).read_text(encoding="utf-8")
    assert '"100vh"' in src and "bodyScrollHeight" in src
    assert 'host.getInt("height")' in src, "the hosting View's height must be asserted too"


def test_the_shell_delivers_a_json_string_not_an_object():
    """`deliver` takes a JSON STRING -- a WebView bridge carries strings reliably and the
    page parses with JSON.parse. Interpolating the envelope as a JS object literal made
    real pages throw `"[object Object]" is not valid JSON` inside the page, where nothing
    could see it. Both the shell AND the fixture had this wrong, so they agreed."""
    src = (PLUGIN / "runtime" / "templates" / "kinds" / "web-shell" / "app" / "src"
           / "main" / "java" / "bridge" / "CommandServer.kt").read_text(encoding="utf-8")
    assert "deliver($payload)" in src, "the delivered payload must be the quoted literal"
    assert "JsonPrimitive(" in src.split("val payload")[1][:200], (
        "the payload must be encoded as a JSON string literal, not interpolated raw"
    )
    assert "deliver($js)" not in src, "the raw-object interpolation must be gone"


def test_the_fixture_parses_the_payload_as_a_string():
    """A fixture that takes an object cannot detect a shell that sends one."""
    js = (ROOT / "tests" / "data" / "web" / "assets" / "app-D4f8a1c2.js").read_text(encoding="utf-8")
    assert "deliver: function (json)" in js
    assert "JSON.parse(json)" in js


def test_the_command_path_is_covered_on_device():
    src = (PLUGIN / "runtime" / "templates" / "kinds" / "web-shell" / "app" / "src"
           / "androidTest" / "java" / "WebShellTest.kt").read_text(encoding="utf-8")
    assert "aCommandRoundTripsThroughTheBridge" in src
    assert "is not valid JSON" in src, "the round-trip must assert the page did not throw"
