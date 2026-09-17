#!/usr/bin/env python3
"""
webdetect -- turn a web project into a built bundle that `scaffold.py --web-dir` accepts.

    webdetect.py detect DIR               what is this project, and how is it built (JSON)
    webdetect.py locate DIR [--output D]  find the built bundle's index.html (JSON); exit 1 if none
    webdetect.py build DIR [--no-install] install, build, then locate a bundle NEWER than the build

Every command prints one JSON object on stdout. `build` streams the package manager's own
output to stderr, so stdout stays parseable.

WHERE THE KNOWLEDGE COMES FROM. `runtime/data/web-frameworks.json` is Vercel's framework
table (@vercel/frameworks, Apache-2.0), vendored as data by scripts/vendor-web-frameworks.mjs.
`matches()` below is a port of `matches()` + `removeSupersededFrameworks()` from
@vercel/fs-detectors 7.3.0 `detect-framework.js`; the comments name the upstream behaviour
each branch reproduces. Keep it a port: if detection disagrees with Vercel's, the port is wrong.

A DETECTED OUTPUT DIRECTORY IS A GUESS. The table's `outputDirectory` is the framework's
default, and projects override it (vite `build.outDir`, Angular's `dist/<project>/browser`,
Next's `out` for a static export). So `locate` never trusts it: the bundle is wherever a
built `index.html` actually is, and `build` additionally requires that index.html to be
newer than the build it just ran -- a stale `dist/` from last week is not this build.

WHAT THIS CANNOT SEE. A server-rendered app (Next without `output: 'export'`, Nuxt SSR,
Remix, SvelteKit without adapter-static) builds successfully and produces no index.html;
`locate` refuses it, which is correct, but cannot tell you which config flag makes it
static. An index.html that exists but fetches `/api/...` from a server will pass here and
fail on the phone. Monorepos: DIR must be the web package itself; nothing here walks
workspaces.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = os.path.join(HERE, "..", "data", "web-frameworks.json")

# Never descended into while searching an output directory. Dot-directories are skipped too.
# (The project root itself is never walked -- see locate() -- so source dirs need no entry.)
SKIP_DIRS = {"node_modules"}

# Where bundles land when the framework default was overridden or is not static.
# `public` is excluded on purpose: in most frameworks it is the SOURCE of static assets,
# and its index.html (CRA, Vite templates) is an unbuilt template.
FALLBACK_OUTPUTS = ("dist", "build", "out", ".output/public", "www", "_site")

LOCKFILES = (  # first match wins; mirrors how the package managers themselves resolve
    ("bun.lock", "bun"),
    ("bun.lockb", "bun"),
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("package-lock.json", "npm"),
    ("npm-shrinkwrap.json", "npm"),
)


def load_table(path: str = TABLE) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Detection -- a port of @vercel/fs-detectors, reading from a real directory
# ---------------------------------------------------------------------------
def _check(root: str, item: dict, slug: str):
    """One detector item. Returns None (no match) or a dict, possibly carrying a version."""
    path = item.get("path")
    match_content = item.get("matchContent")
    match_package = item.get("matchPackage")
    # upstream throws on these combinations; a malformed vendored table should be loud too
    if match_package and (match_content or path):
        raise ValueError(f"{slug}: matchPackage cannot combine with path/matchContent")
    if not path and not match_package:
        raise ValueError(f"{slug}: detector needs path or matchPackage")
    if not path:
        path = "package.json"
    if match_package:
        match_content = (
            '"(dev)?(d|D)ependencies":\\s*{[^}]*"'
            + re.escape(match_package)
            + '":\\s*"(.+?)"[^}]*}'
        )
    full = os.path.join(root, path)
    if not os.path.exists(full):  # upstream hasPath: files and directories
        return None
    if match_content:
        if not os.path.isfile(full):
            return None
        with open(full, encoding="utf-8", errors="replace") as fh:
            m = re.search(match_content, fh.read(), re.M)
        if not m:
            return None
        if match_package and m.group(3):
            return {"version": m.group(3)}
    return {}


def matches(root: str, framework: dict):
    """Upstream `matches()`: every `every` item must match, and at least one `some` item."""
    detectors = framework.get("detectors")
    if not detectors:
        return None
    slug = framework.get("slug")
    results = [_check(root, it, slug) for it in detectors.get("every", [])]
    if "some" in detectors:
        some = None
        for it in detectors["some"]:
            some = _check(root, it, slug)
            if some is not None:
                break
        results.append(some)
    if any(r is None for r in results):
        return None
    version = next((r["version"] for r in results if r.get("version")), None)
    return {"version": version}


def remove_superseded(matched: list) -> list:
    """Upstream `removeSupersededFrameworks()`: vite is dropped when e.g. astro also matched."""
    out = list(matched)

    def drop(slug):
        idx = next((i for i, f in enumerate(out) if f["slug"] == slug), None)
        if idx is None:
            return
        f = out[idx]
        for s in f.get("supersedes", []):
            drop(s)
        out.pop(out.index(f))

    for f in list(matched):
        for s in f.get("supersedes", []):
            drop(s)
    return out


def detect_framework(root: str, table: dict) -> dict | None:
    """First surviving match in table order, with the detected version. None if none."""
    matched = []
    for f in table["frameworks"]:
        r = matches(root, f)
        if r is not None:
            matched.append({**f, "detectedVersion": r["version"]})
    survivors = remove_superseded(matched)
    return survivors[0] if survivors else None


# ---------------------------------------------------------------------------
# The build plan -- pure: files in, decisions out
# ---------------------------------------------------------------------------
def read_package_json(root: str) -> dict | None:
    p = os.path.join(root, "package.json")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def package_manager(root: str, pkg: dict | None) -> tuple[str, str]:
    """(manager, why). `packageManager` (corepack) beats lockfiles; npm is the default."""
    field = (pkg or {}).get("packageManager")
    if isinstance(field, str) and "@" in field:
        name = field.split("@", 1)[0]
        if name in ("npm", "pnpm", "yarn", "bun"):
            return name, f'package.json "packageManager": "{field}"'
    for lock, name in LOCKFILES:
        if os.path.isfile(os.path.join(root, lock)):
            return name, lock
    return "npm", "no lockfile; npm by default"


def install_command(manager: str, root: str) -> list[str]:
    if manager == "npm":
        # `npm ci` refuses without a lockfile, and is the reproducible install when there is one
        has_lock = any(os.path.isfile(os.path.join(root, f)) for f in ("package-lock.json", "npm-shrinkwrap.json"))
        return ["npm", "ci"] if has_lock else ["npm", "install"]
    if manager == "pnpm":
        return ["pnpm", "install", "--frozen-lockfile"]
    return [manager, "install"]


def vite_out_dir(root: str) -> str | None:
    """`build.outDir` from vite.config.*, by regex. The config is code, so this can miss it;
    it is a hint for `locate`, never the proof."""
    for name in ("vite.config.ts", "vite.config.mts", "vite.config.js", "vite.config.mjs", "vite.config.cjs"):
        p = os.path.join(root, name)
        if os.path.isfile(p):
            with open(p, encoding="utf-8", errors="replace") as fh:
                m = re.search(r"""outDir\s*:\s*['"`]([^'"`]+)['"`]""", fh.read())
            if m:
                return m.group(1)
    return None


def plan(root: str, table: dict) -> dict:
    """Everything `detect` reports. No process is spawned."""
    root = os.path.abspath(root)
    pkg = read_package_json(root)
    fw = detect_framework(root, table)
    has_root_index = os.path.isfile(os.path.join(root, "index.html"))

    if pkg is None:
        if fw is None and has_root_index:
            return {
                "root": root, "kind": "static", "framework": None,
                "install": None, "build": None,
                "output": {"dir": ".", "why": "no package.json; index.html at the root is the bundle"},
                "warnings": ["the whole directory is the bundle -- scaffold copies everything in it"],
            }
        if fw is None:
            return {"root": root, "kind": "unknown", "framework": None, "install": None,
                    "build": None, "output": None,
                    "warnings": ["no package.json and no index.html: not a web project this can build"]}

    warnings = []
    manager, manager_why = package_manager(root, pkg)
    scripts = (pkg or {}).get("scripts") or {}
    settings = (fw or {}).get("settings") or {}
    fw_build = settings.get("buildCommand") or {}

    # Upstream build-utils order: a package.json "build" script wins, unless the framework
    # says to ignore it (ignorePackageJsonScript); then the framework's own command.
    if "build" in scripts and not fw_build.get("ignorePackageJsonScript"):
        build = {"argv": [manager, "run", "build"], "why": f'package.json scripts.build: {scripts["build"]}'}
    elif fw_build.get("value"):
        exec_prefix = {"npm": ["npx", "--no-install"], "bun": ["bunx"]}.get(manager, [manager, "exec"])
        build = {"argv": [*exec_prefix, *fw_build["value"].split()],
                 "why": f"{fw['name']} default build command"}
    else:
        build = None
        warnings.append("no build script and no framework build command: nothing to run")

    candidates = []
    vod = vite_out_dir(root) if fw and fw["slug"] == "vite" else None
    if vod:
        candidates.append({"dir": vod, "why": "vite.config build.outDir (regex)"})
    # A framework with a server runtime (Next, Remix, Express...) has no static default:
    # its table entry says "N/A" or `public`, which is a SOURCE directory. Only the
    # fallbacks can find its static export (Next: `out`).
    fw_out = None
    if fw and not fw.get("useRuntime"):
        fw_out = (settings.get("outputDirectory") or {}).get("value") or fw.get("defaultOutputDir")
    if fw_out:
        candidates.append({"dir": fw_out, "why": f"{fw['name']} default output directory"})
    for d in FALLBACK_OUTPUTS:
        if all(c["dir"] != d for c in candidates):
            candidates.append({"dir": d, "why": "common output directory"})

    if fw and fw.get("useRuntime"):
        warnings.append(f"{fw['name']} deploys with a server runtime ({fw['useRuntime']}); "
                        "a web-shell needs a static export")

    return {
        "root": root,
        "kind": "framework" if fw else "package",
        "framework": ({"slug": fw["slug"], "name": fw["name"], "version": fw["detectedVersion"]} if fw else None),
        "packageManager": {"name": manager, "why": manager_why},
        "install": {"argv": install_command(manager, root)},
        "build": build,
        "output": {"candidates": candidates},
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Locating the bundle -- the only proof that counts
# ---------------------------------------------------------------------------
def _index_files(base: str, max_depth: int = 2) -> list[str]:
    """index.html files at most `max_depth` directories below `base` (Angular: dist/<p>/browser)."""
    found = []
    base_depth = base.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(base):
        depth = dirpath.rstrip(os.sep).count(os.sep) - base_depth
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        if depth >= max_depth:
            dirnames[:] = []
        if "index.html" in filenames:
            found.append(os.path.join(dirpath, "index.html"))
    return found


def locate(root: str, candidates: list[dict], newer_than: float | None = None) -> dict:
    """Return {"ok": True, "webDir": ..., ...} for the first candidate holding exactly one
    shallowest index.html (newer than `newer_than` if given), else {"ok": False, "reason": ...}."""
    root = os.path.abspath(root)
    looked = []
    for c in candidates:
        base = os.path.normpath(os.path.join(root, c["dir"]))
        if not os.path.isdir(base):
            looked.append(f"{c['dir']}: absent")
            continue
        found = _index_files(base) if base != root else (
            [os.path.join(root, "index.html")] if os.path.isfile(os.path.join(root, "index.html")) else [])
        if newer_than is not None:
            stale = [f for f in found if os.path.getmtime(f) < newer_than]
            found = [f for f in found if f not in stale]
            if stale and not found:
                looked.append(f"{c['dir']}: index.html is older than this build (stale)")
                continue
        if not found:
            looked.append(f"{c['dir']}: no index.html")
            continue
        shallowest = min(f.count(os.sep) for f in found)
        top = [f for f in found if f.count(os.sep) == shallowest]
        if len(top) > 1:
            return {"ok": False, "reason": f"{c['dir']}: more than one bundle -- pass --output",
                    "found": [os.path.relpath(f, root) for f in top]}
        web_dir = os.path.dirname(top[0])
        return {"ok": True, "webDir": web_dir, "why": c["why"],
                "builtAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(os.path.getmtime(top[0]))),
                "looked": looked}
    return {"ok": False, "reason": "no built index.html in any candidate output directory", "looked": looked}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _emit(obj: dict, rc: int = 0) -> int:
    print(json.dumps(obj, indent=2))
    return rc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="webdetect.py", description=__doc__.split("\n\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("detect", "locate", "build"):
        p = sub.add_parser(name)
        p.add_argument("dir")
        if name in ("locate", "build"):
            p.add_argument("--output", help="the output directory, when detection cannot know it")
        if name == "build":
            p.add_argument("--no-install", action="store_true", help="skip the install step")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.dir):
        return _emit({"ok": False, "reason": f"{args.dir}: not a directory"}, 2)
    p = plan(args.dir, load_table())
    if args.cmd == "detect":
        return _emit(p)

    candidates = ([{"dir": args.output, "why": "--output"}] if args.output
                  else (p["output"] or {}).get("candidates") or ([p["output"]] if p.get("output") else []))

    if args.cmd == "locate":
        r = locate(args.dir, candidates)
        return _emit({**r, "plan": p}, 0 if r["ok"] else 1)

    # build
    if p["kind"] == "static":
        r = locate(args.dir, candidates)
        return _emit({**r, "plan": p, "ran": []}, 0 if r["ok"] else 1)
    if not p.get("build"):
        return _emit({"ok": False, "reason": "nothing to build", "plan": p}, 1)
    ran = []
    steps = [] if args.no_install else [p["install"]["argv"]]
    steps.append(p["build"]["argv"])
    started = time.time() - 2  # filesystem mtime granularity
    for step in steps:
        print(f"webdetect: $ {' '.join(step)}", file=sys.stderr)
        try:
            rc = subprocess.call(step, cwd=p["root"], stdout=sys.stderr)
        except FileNotFoundError:
            return _emit({"ok": False, "reason": f"{step[0]}: not on PATH", "plan": p, "ran": ran}, 1)
        ran.append({"argv": step, "rc": rc})
        if rc != 0:
            return _emit({"ok": False, "reason": f"`{' '.join(step)}` exited {rc}", "plan": p, "ran": ran}, 1)
    r = locate(args.dir, candidates, newer_than=started)
    return _emit({**r, "plan": p, "ran": ran}, 0 if r["ok"] else 1)


if __name__ == "__main__":
    sys.exit(main())
