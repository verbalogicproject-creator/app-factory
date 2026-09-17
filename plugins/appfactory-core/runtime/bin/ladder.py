#!/usr/bin/env python3
"""
ladder -- the pure parts of the local verification ladder.

    ladder.py stages [--until STAGE] STAGE...      ordered stages incl. prerequisites
    ladder.py receipt --kind run|bench --host H --out DIR [--stage NAME=RC=SECONDS ...]
                      [--artifact PATH ...] [--tree DIR] [--jdk X] [--gradle-wrapper X]
                      [--aapt2 X]                  write <utc>-<kind>.json, print its path
    ladder.py validate FILE                        exit 1 if the receipt is malformed
    ladder.py parse-instrument < am-instrument.log  print tests= failures= ok=; exit 1 if not ok

WHY A PYTHON FILE. `local-build.sh` orchestrates Gradle and adb -- that needs a shell and
a device. The decisions inside it (what runs before what, what a receipt looks like, what
"OK (12 tests)" means) do not, and a decision that can be made pure is a decision that
`pytest` can cover. The shell calls in here; it does not re-implement any of it.

A RECEIPT IS EVIDENCE ABOUT ONE TREE. It records the git sha and whether the tree was
dirty, because a green run carried forward across a later change is not coverage --
that mistake once put a broken assertion on a remote branch.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone

STAGES = ["preflight", "compile", "unit", "lint", "debug", "verify-apk", "instrumented", "device", "release"]

# A stage's prerequisites, by name. `release` needs the release APK verified, which is
# its own step; `instrumented` needs the debug + androidTest APKs `debug` builds.
PREREQS = {
    "verify-apk": ["debug"],
    "instrumented": ["debug"],
    # `device` probes the app the USER installed from that debug APK -- no adb (device-probe.sh).
    "device": ["debug"],
    "release": ["verify-apk"],
}

SCHEMA = 1


def expand(requested, until=None):
    """Return the ordered subset of STAGES implied by `requested` (+ prerequisites)."""
    wanted = set()
    for s in requested:
        if s not in STAGES:
            raise ValueError(f"unknown stage: {s} (known: {', '.join(STAGES)})")
        wanted.add(s)
    if until is not None:
        if until not in STAGES:
            raise ValueError(f"unknown stage: {until}")
        wanted.update(STAGES[: STAGES.index(until) + 1])
    # close over prerequisites
    changed = True
    while changed:
        changed = False
        for s in list(wanted):
            for p in PREREQS.get(s, []):
                if p not in wanted:
                    wanted.add(p)
                    changed = True
    return [s for s in STAGES if s in wanted]


def parse_stage_arg(text):
    """'name=rc=seconds' -> dict. rc and seconds must parse; name must be a stage."""
    parts = text.split("=")
    if len(parts) != 3:
        raise ValueError(f"stage must be NAME=RC=SECONDS, got {text!r}")
    name, rc, secs = parts
    if name not in STAGES:
        raise ValueError(f"unknown stage: {name}")
    return {"name": name, "rc": int(rc), "seconds": round(float(secs), 3)}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_state(tree):
    """{'sha': ..., 'dirty': bool} for a git tree; sha None if not a repo."""
    try:
        sha = subprocess.run(["git", "-C", tree, "rev-parse", "HEAD"], capture_output=True,
                             text=True, check=True).stdout.strip()
        status = subprocess.run(["git", "-C", tree, "status", "--porcelain"], capture_output=True,
                                text=True, check=True).stdout
        return {"sha": sha, "dirty": bool(status.strip())}
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {"sha": None, "dirty": None}


def build_receipt(kind, host, stages, artifacts, tree, toolchain):
    started = datetime.now(timezone.utc).replace(microsecond=0)
    arts = []
    for p in artifacts:
        if not os.path.isfile(p):
            raise ValueError(f"artifact does not exist: {p}")
        arts.append({"path": p, "sha256": sha256_of(p), "bytes": os.path.getsize(p)})
    return {
        "schema": SCHEMA,
        "kind": kind,
        "host": host,
        "host_arch": platform.machine(),
        "started": started.isoformat().replace("+00:00", "Z"),
        "tree": tree_state(tree),
        "toolchain": toolchain,
        "stages": stages,
        "artifacts": arts,
    }


def validate_receipt(doc):
    """Return a list of problems; empty means valid."""
    problems = []
    if doc.get("schema") != SCHEMA:
        problems.append(f"schema must be {SCHEMA}")
    if doc.get("kind") not in ("run", "bench"):
        problems.append("kind must be run|bench")
    if not isinstance(doc.get("host"), str) or not doc["host"]:
        problems.append("host missing")
    tree = doc.get("tree")
    if not isinstance(tree, dict) or "sha" not in tree or "dirty" not in tree:
        problems.append("tree must carry sha and dirty")
    stages = doc.get("stages")
    if not isinstance(stages, list) or not stages:
        problems.append("stages must be a non-empty list")
    else:
        seen = []
        for s in stages:
            if not isinstance(s, dict) or set(s) != {"name", "rc", "seconds"}:
                problems.append(f"bad stage entry: {s!r}")
                continue
            if s["name"] not in STAGES:
                problems.append(f"unknown stage: {s['name']}")
            seen.append(s["name"])
        order = [STAGES.index(n) for n in seen if n in STAGES]
        if order != sorted(order):
            problems.append("stages are not in ladder order")
    for a in doc.get("artifacts", []):
        if set(a) != {"path", "sha256", "bytes"} or not re.fullmatch(r"[0-9a-f]{64}", a.get("sha256", "")):
            problems.append(f"bad artifact entry: {a!r}")
    return problems


INSTR_OK = re.compile(r"^OK \((\d+) tests?\)\s*$", re.M)
INSTR_FAIL = re.compile(r"^Tests run: (\d+),\s+Failures: (\d+)", re.M)
INSTR_FAILURES = re.compile(r"^FAILURES!!!", re.M)
INSTR_CRASH = re.compile(r"INSTRUMENTATION_RESULT: shortMsg=|INSTRUMENTATION_STATUS: Error=|Process crashed", re.M)


def parse_instrument(text):
    """Interpret `am instrument -w` output. Zero tests is NOT ok -- a suite that ran
    nothing reports success and verifies nothing."""
    if INSTR_CRASH.search(text):
        return {"tests": 0, "failures": 0, "ok": False, "reason": "instrumentation crashed"}
    m = INSTR_FAIL.search(text)
    if m:
        tests, failures = int(m.group(1)), int(m.group(2))
        return {"tests": tests, "failures": failures, "ok": False, "reason": "failures"}
    if INSTR_FAILURES.search(text):
        return {"tests": 0, "failures": 0, "ok": False, "reason": "FAILURES!!! without a count"}
    m = INSTR_OK.search(text)
    if m:
        n = int(m.group(1))
        if n == 0:
            return {"tests": 0, "failures": 0, "ok": False, "reason": "zero tests ran"}
        return {"tests": n, "failures": 0, "ok": True, "reason": ""}
    return {"tests": 0, "failures": 0, "ok": False, "reason": "no result line found"}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ladder.py")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("stages")
    s.add_argument("--until")
    s.add_argument("stage", nargs="*")

    r = sub.add_parser("receipt")
    r.add_argument("--kind", choices=("run", "bench"), required=True)
    r.add_argument("--host", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--stage", action="append", default=[])
    r.add_argument("--artifact", action="append", default=[])
    r.add_argument("--tree", default=".")
    r.add_argument("--jdk", default="")
    r.add_argument("--gradle-wrapper", default="")
    r.add_argument("--aapt2", default="")

    v = sub.add_parser("validate")
    v.add_argument("file")

    sub.add_parser("parse-instrument")

    a = ap.parse_args(argv)
    try:
        if a.cmd == "stages":
            if not a.stage and not a.until:
                raise ValueError("give at least one stage or --until")
            print("\n".join(expand(a.stage, a.until)))
            return 0
        if a.cmd == "receipt":
            stages = [parse_stage_arg(t) for t in a.stage]
            if not stages:
                raise ValueError("a receipt needs at least one --stage")
            doc = build_receipt(a.kind, a.host, stages, a.artifact, a.tree,
                                {"jdk": a.jdk, "gradle_wrapper": a.gradle_wrapper, "aapt2": a.aapt2})
            probs = validate_receipt(doc)
            if probs:
                raise ValueError("; ".join(probs))
            os.makedirs(a.out, exist_ok=True)
            name = doc["started"].replace(":", "") + f"-{a.kind}.json"
            path = os.path.join(a.out, name)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2)
                f.write("\n")
            print(path)
            return 0
        if a.cmd == "validate":
            with open(a.file, encoding="utf-8") as f:
                probs = validate_receipt(json.load(f))
            for p in probs:
                print(f"FAIL {p}")
            return 1 if probs else 0
        if a.cmd == "parse-instrument":
            res = parse_instrument(sys.stdin.read())
            print(f"tests={res['tests']} failures={res['failures']} ok={'true' if res['ok'] else 'false'}"
                  + (f" reason={res['reason']}" if res["reason"] else ""))
            return 0 if res["ok"] else 1
    except ValueError as e:
        print(f"ladder: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
