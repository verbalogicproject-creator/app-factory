"""Tests for runtime/bin/webdetect.py -- web project detection, build plan, bundle location."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time

import pytest

from tests.conftest import RUNTIME_BIN, load_module

webdetect = load_module("webdetect", RUNTIME_BIN / "webdetect.py")
TABLE = webdetect.load_table()


def _project(tmp_path, pkg=None, files=()):
    root = tmp_path / "proj"
    root.mkdir()
    if pkg is not None:
        (root / "package.json").write_text(json.dumps(pkg, indent=2))
    for rel in files:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("<!doctype html><title>x</title>" if rel.endswith(".html") else "")
    return root


# ---------------------------------------------------------------------------
# The vendored table
# ---------------------------------------------------------------------------
def test_table_records_its_provenance():
    src = TABLE["source"]
    assert src["package"] == "@vercel/frameworks"
    assert src["license"] == "Apache-2.0"
    assert re.fullmatch(r"\d+\.\d+\.\d+", src["version"])


def test_every_vendored_matcher_compiles_as_a_python_regex():
    # The table's regexes were written for JavaScript. One that Python rejects would
    # surface as a crash on the first project that reaches that framework.
    for f in TABLE["frameworks"]:
        for kind in ("every", "some"):
            for item in (f.get("detectors") or {}).get(kind, []):
                if "matchContent" in item:
                    re.compile(item["matchContent"], re.M)


def test_every_detector_is_well_formed(tmp_path):
    # _check raises on the combinations upstream throws on; run every item once.
    for f in TABLE["frameworks"]:
        for kind in ("every", "some"):
            for item in (f.get("detectors") or {}).get(kind, []):
                webdetect._check(str(tmp_path), item, f["slug"])


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
def test_vite_detected_with_its_declared_version(tmp_path):
    root = _project(tmp_path, {"devDependencies": {"vite": "^8.1.5"}})
    fw = webdetect.detect_framework(str(root), TABLE)
    assert fw["slug"] == "vite"
    assert fw["detectedVersion"] == "^8.1.5"


def test_a_package_named_only_in_scripts_is_not_a_dependency(tmp_path):
    root = _project(tmp_path, {"scripts": {"build": "vite build"}})
    assert webdetect.detect_framework(str(root), TABLE) is None


def test_superseded_framework_is_removed(tmp_path):
    # sveltekit-1 declares supersedes: ["vite"]; both match, sveltekit must win
    root = _project(tmp_path, {"devDependencies": {"vite": "5", "@sveltejs/kit": "1"}})
    assert webdetect.detect_framework(str(root), TABLE)["slug"] == "sveltekit-1"


def test_some_detector_needs_only_one_match(tmp_path):
    root = _project(tmp_path, {"dependencies": {"react-dev-utils": "12"}})
    assert webdetect.detect_framework(str(root), TABLE)["slug"] == "create-react-app"


def test_remove_superseded_is_transitive():
    matched = [{"slug": "a", "supersedes": ["b"]}, {"slug": "b", "supersedes": ["c"]}, {"slug": "c"}]
    assert [f["slug"] for f in webdetect.remove_superseded(matched)] == ["a"]


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------
def test_static_site_without_package_json(tmp_path):
    root = _project(tmp_path, files=["index.html"])
    p = webdetect.plan(str(root), TABLE)
    assert p["kind"] == "static"
    assert p["build"] is None
    assert p["output"]["dir"] == "."


def test_nothing_recognisable_says_so(tmp_path):
    root = _project(tmp_path, files=["README.md"])
    p = webdetect.plan(str(root), TABLE)
    assert p["kind"] == "unknown"
    assert p["warnings"]


def test_build_script_beats_framework_command(tmp_path):
    root = _project(tmp_path, {"scripts": {"build": "tsc && vite build"}, "devDependencies": {"vite": "5"}},
                    files=["package-lock.json"])
    p = webdetect.plan(str(root), TABLE)
    assert p["build"]["argv"] == ["npm", "run", "build"]
    assert p["install"]["argv"] == ["npm", "ci"]


def test_framework_command_used_when_no_build_script(tmp_path):
    root = _project(tmp_path, {"devDependencies": {"vite": "5"}})
    p = webdetect.plan(str(root), TABLE)
    assert p["build"]["argv"] == ["npx", "--no-install", "vite", "build"]
    assert p["install"]["argv"] == ["npm", "install"]  # no lockfile: `npm ci` would refuse


def test_ignore_package_json_script_is_honoured(tmp_path):
    fw = next(f for f in TABLE["frameworks"] if (f["settings"]["buildCommand"] or {}).get("ignorePackageJsonScript"))
    pkg_name = next(it["matchPackage"] for k in ("every", "some") for it in fw["detectors"].get(k, []) if "matchPackage" in it)
    root = _project(tmp_path, {"scripts": {"build": "something else"}, "devDependencies": {pkg_name: "1"}})
    p = webdetect.plan(str(root), TABLE)
    assert p["framework"]["slug"] == fw["slug"]
    cmd = fw["settings"]["buildCommand"]["value"].split()
    assert p["build"]["argv"][-len(cmd):] == cmd


@pytest.mark.parametrize("lock,manager", [
    ("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun"), ("package-lock.json", "npm"),
])
def test_package_manager_from_lockfile(tmp_path, lock, manager):
    root = _project(tmp_path, {"scripts": {"build": "x"}}, files=[lock])
    assert webdetect.plan(str(root), TABLE)["packageManager"]["name"] == manager


def test_package_manager_field_beats_lockfile(tmp_path):
    root = _project(tmp_path, {"packageManager": "pnpm@9.1.0", "scripts": {"build": "x"}}, files=["package-lock.json"])
    p = webdetect.plan(str(root), TABLE)
    assert p["packageManager"]["name"] == "pnpm"
    assert p["build"]["argv"] == ["pnpm", "run", "build"]


def test_vite_out_dir_is_the_first_candidate(tmp_path):
    root = _project(tmp_path, {"devDependencies": {"vite": "5"}})
    (root / "vite.config.ts").write_text("export default { build: { outDir: 'www-out' } }")
    cands = webdetect.plan(str(root), TABLE)["output"]["candidates"]
    assert cands[0] == {"dir": "www-out", "why": "vite.config build.outDir (regex)"}
    assert cands[1]["dir"] == "dist"


def test_server_framework_warns_and_never_offers_public(tmp_path):
    # Next's table entry says `public` -- a SOURCE directory. Offering it would pick up
    # whatever index.html sits in public/ and call it a bundle.
    root = _project(tmp_path, {"dependencies": {"next": "15"}, "scripts": {"build": "next build"}})
    p = webdetect.plan(str(root), TABLE)
    assert p["framework"]["slug"] == "nextjs"
    assert "public" not in [c["dir"] for c in p["output"]["candidates"]]
    assert "out" in [c["dir"] for c in p["output"]["candidates"]]
    assert any("static export" in w for w in p["warnings"])


# ---------------------------------------------------------------------------
# Locating the bundle
# ---------------------------------------------------------------------------
CANDS = [{"dir": "dist", "why": "d"}, {"dir": "build", "why": "b"}]


def test_locate_finds_first_candidate_with_index(tmp_path):
    root = _project(tmp_path, files=["build/index.html"])
    r = webdetect.locate(str(root), CANDS)
    assert r["ok"] and r["webDir"] == str(root / "build")
    assert r["looked"] == ["dist: absent"]


def test_locate_descends_into_a_single_nested_bundle(tmp_path):
    # Angular 17+: dist/<project>/browser/index.html -- including a project named "app"
    root = _project(tmp_path, files=["dist/app/browser/index.html"])
    r = webdetect.locate(str(root), CANDS)
    assert r["ok"] and r["webDir"] == str(root / "dist" / "app" / "browser")


def test_locate_prefers_the_shallowest_index(tmp_path):
    root = _project(tmp_path, files=["dist/index.html", "dist/docs/index.html"])
    assert webdetect.locate(str(root), CANDS)["webDir"] == str(root / "dist")


def test_locate_refuses_two_bundles_at_the_same_depth(tmp_path):
    root = _project(tmp_path, files=["dist/a/index.html", "dist/b/index.html"])
    r = webdetect.locate(str(root), CANDS)
    assert not r["ok"] and "--output" in r["reason"]


def test_locate_ignores_node_modules(tmp_path):
    root = _project(tmp_path, files=["dist/node_modules/x/index.html"])
    assert not webdetect.locate(str(root), CANDS)["ok"]


def test_locate_rejects_a_stale_bundle(tmp_path):
    root = _project(tmp_path, files=["dist/index.html"])
    old = time.time() - 3600
    os.utime(root / "dist" / "index.html", (old, old))
    r = webdetect.locate(str(root), CANDS, newer_than=time.time() - 60)
    assert not r["ok"]
    assert "dist: index.html is older than this build (stale)" in r["looked"]


def test_locate_reports_every_place_it_looked(tmp_path):
    root = _project(tmp_path, files=["dist/app.js"])
    r = webdetect.locate(str(root), CANDS)
    assert not r["ok"]
    assert r["looked"] == ["dist: no index.html", "build: absent"]


# ---------------------------------------------------------------------------
# CLI end to end -- spawns node, so excluded from the fast run
# ---------------------------------------------------------------------------
@pytest.mark.slow
@pytest.mark.skipif(shutil.which("npm") is None, reason="npm not installed")
def test_build_runs_the_script_and_returns_a_fresh_bundle(tmp_path):
    root = _project(tmp_path, {
        "name": "t", "private": True,
        "scripts": {"build": "node -e \"require('fs').mkdirSync('dist',{recursive:true});"
                             "require('fs').writeFileSync('dist/index.html','<title>t</title>')\""},
    })
    proc = subprocess.run([sys.executable, str(RUNTIME_BIN / "webdetect.py"), "build", str(root), "--no-install"],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["ok"] and out["webDir"] == str(root / "dist")
    assert out["ran"] == [{"argv": ["npm", "run", "build"], "rc": 0}]


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("npm") is None, reason="npm not installed")
def test_build_that_writes_nothing_fails_even_with_an_old_dist(tmp_path):
    root = _project(tmp_path, {"name": "t", "private": True, "scripts": {"build": "node -e 0"}},
                    files=["dist/index.html"])
    old = time.time() - 3600
    os.utime(root / "dist" / "index.html", (old, old))
    proc = subprocess.run([sys.executable, str(RUNTIME_BIN / "webdetect.py"), "build", str(root), "--no-install"],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 1
    assert "stale" in " ".join(json.loads(proc.stdout)["looked"])
