#!/usr/bin/env python3
"""
contract -- the decisions an app is built from, written down before any code exists.

    contract.py init --out DIR --application-id ID --app-name NAME [options]
    contract.py validate DIR [--date YYYY-MM-DD]
    contract.py show DIR
    contract.py target-sdk-floor [--date YYYY-MM-DD] [--check PATH]

Writes and checks `.appfactory/contract/`:
    lattice.toml     machine-readable decisions + the adopted version lattice
    decisions.md     the irreversible ones, with the consequence of changing each
    UNVERIFIED.md    every guessed value, as `- [ ] claim | why unverified | how to verify`

WHY A FILE AND NOT A CONVERSATION. Two things about an Android app have no migration
path after the first install (applicationId, signing certificate) and one is
migration-sensitive (the persisted schema). Settling them in prose leaves nothing to
diff or point at when someone later asks why the id is what it is. `bootstrap` reads
this instead of re-interviewing, and keeps working with no contract present.

THE targetSdk NUMBER HAS ONE HOME: the dated table inside preflight check 140. This
tool parses that table rather than carrying a copy, so the generator's default can
never again be a value the generator's own gate rejects.
"""
import argparse
import json
import os
import re
import sys
import tomllib
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
APPLICATION_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*$")
KINDS = ("compose", "web-shell")
UNVERIFIED_LINE = re.compile(r"^- \[[ x]\] (?P<claim>[^|]+?) \| (?P<why>[^|]+?) \| (?P<how>[^|]+?)\s*$")

IRREVERSIBLE = (
    ("applicationId", "application_id", "a different app entirely; every existing install is orphaned"),
    ("signing certificate", "signing_profile", "no installed device will ever accept an update. No recovery."),
    ("persisted schema version", "schema_version", "v2 must migrate from v1 or destroy user data"),
)


def find_check_140():
    for c in (os.path.join(HERE, "..", "scripts", "preflight", "checks", "140-target-sdk-submittable.sh"),
              os.path.join(HERE, "..", "..", "scripts", "preflight", "checks", "140-target-sdk-submittable.sh")):
        if os.path.isfile(c):
            return os.path.normpath(c)
    return None


def parse_requirements(check_path):
    """The REQUIREMENTS heredoc in check 140: rows of `YYYY-MM-DD N`."""
    text = open(check_path, encoding="utf-8").read()
    m = re.search(r'REQUIREMENTS="\n(.*?)\n"', text, re.S)
    if not m:
        raise ValueError(f"no REQUIREMENTS table in {check_path}")
    rows = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line:
            continue
        eff, sdk = line.split()
        rows.append((date.fromisoformat(eff), int(sdk)))
    if not rows:
        raise ValueError("REQUIREMENTS table is empty")
    return sorted(rows)


def target_sdk_floor(rows, today, horizon_days=120):
    """Highest requirement already in force; if the next one lands within `horizon_days`,
    take it instead -- an app generated today is submitted later."""
    required = max((sdk for eff, sdk in rows if eff <= today), default=0)
    nxt = [(eff, sdk) for eff, sdk in rows if eff > today]
    if nxt and (nxt[0][0] - today).days <= horizon_days:
        return max(required, nxt[0][1])
    return required


def find_versions():
    c = os.path.join(HERE, "..", "versions", "2026-08-api36.toml")
    return os.path.normpath(c) if os.path.isfile(c) else None


def toml_scalar(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_toml(doc, path):
    lines = ["# Written by contract.py. Edit deliberately; bootstrap reads this instead of re-interviewing.", ""]
    for table, values in doc.items():
        lines.append(f"[{table}]")
        for k, v in values.items():
            lines.append(f"{k} = {toml_scalar(v)}")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def build(a, today):
    unverified = []
    if a.target_sdk is None:
        check = a.check or find_check_140()
        if not check:
            raise ValueError("no check 140 found to derive targetSdk from; pass --target-sdk or --check")
        target = target_sdk_floor(parse_requirements(check), today)
    else:
        target = a.target_sdk
    app = {
        "application_id": a.application_id,
        "app_name": a.app_name,
        "min_sdk": a.min_sdk,
        "target_sdk": target,
        "kind": a.kind,
        "with_native": bool(a.with_native),
        "web_dir": a.web_dir or "",
        "deeplink_scheme": a.deeplink_scheme or "",
        "schema_version": a.schema_version,
        "decided": today.isoformat(),
    }
    doc = {"app": app,
           "repo": {"owner": a.repo.split("/")[0] if a.repo else "", "name": a.repo.split("/")[-1] if a.repo else ""},
           "play": {"package": a.play_package or a.application_id, "track": a.track,
                    "package_registered": bool(a.play_registered)},
           "signing": {"profile": a.signing_profile or ""}}
    versions_path = a.versions or find_versions()
    if versions_path:
        with open(versions_path, "rb") as f:
            doc["versions"] = {k: v for k, v in tomllib.load(f).items() if isinstance(v, (str, int, bool))}
        doc["versions"]["source"] = os.path.basename(versions_path)
    else:
        unverified.append(("version lattice", "no versions file found next to contract.py", "pass --versions"))
    if not a.repo:
        unverified.append(("GitHub repo owner/name", "not given at interview", "create the repo, then set [repo]"))
    if not a.signing_profile:
        unverified.append(("signing profile", "no key generated yet", "pass_manager.py keygen <profile>"))
    if not a.play_registered:
        unverified.append(("Play package exists", "the Play API cannot create an app",
                           "upload one AAB by hand in Play Console, then set package_registered = true"))
    for u in a.unverified or []:
        parts = [p.strip() for p in u.split("|")]
        if len(parts) != 3:
            raise ValueError(f"--unverified needs 'claim | why | how', got {u!r}")
        # A caller restating one of the defaults above replaces it rather than listing the
        # claim twice (found in the v1 acceptance run): the caller's why/how are the more
        # specific ones. Same claim = same text ignoring case and spacing.
        unverified = [x for x in unverified if claim_key(x[0]) != claim_key(parts[0])]
        unverified.append(tuple(parts))
    return doc, unverified


def claim_key(claim):
    return " ".join(claim.lower().split())


def write_all(out, doc, unverified):
    os.makedirs(out, exist_ok=True)
    write_toml(doc, os.path.join(out, "lattice.toml"))
    app = doc["app"]
    with open(os.path.join(out, "decisions.md"), "w", encoding="utf-8") as f:
        f.write(f"# Decisions — {app['app_name']} ({app['decided']})\n\n")
        f.write("Three things cannot be changed cheaply after the first install. Settled first, on purpose.\n\n")
        f.write("| Decision | Value | Consequence of changing it |\n|---|---|---|\n")
        for label, key, consequence in IRREVERSIBLE:
            val = app.get(key, doc["signing"].get("profile", "")) or "UNVERIFIED"
            f.write(f"| {label} | `{val}` | {consequence} |\n")
        f.write(f"\nkind: `{app['kind']}` · minSdk {app['min_sdk']} · targetSdk {app['target_sdk']} "
                f"(from check 140's dated table) · Play track `{doc['play']['track']}`\n")
    with open(os.path.join(out, "UNVERIFIED.md"), "w", encoding="utf-8") as f:
        f.write("# Unverified\n\nEvery line is a guess until a human ticks it. Format: `- [ ] claim | why unverified | how to verify`\n\n")
        for claim, why, how in unverified:
            f.write(f"- [ ] {claim} | {why} | {how}\n")


def validate(out, today, check=None):
    problems = []
    path = os.path.join(out, "lattice.toml")
    if not os.path.isfile(path):
        return [f"missing {path}"]
    with open(path, "rb") as f:
        doc = tomllib.load(f)
    app = doc.get("app", {})
    if not APPLICATION_ID_RE.match(str(app.get("application_id", ""))):
        problems.append("app.application_id is not a valid applicationId")
    if not str(app.get("app_name", "")).strip():
        problems.append("app.app_name is empty")
    if not isinstance(app.get("min_sdk"), int) or app["min_sdk"] < 26:
        problems.append("app.min_sdk must be an int >= 26 (adaptive icons)")
    check = check or find_check_140()
    if check:
        floor = target_sdk_floor(parse_requirements(check), today)
        if not isinstance(app.get("target_sdk"), int) or app["target_sdk"] < floor:
            problems.append(f"app.target_sdk {app.get('target_sdk')} is below Play's floor {floor} (check 140)")
    if app.get("kind") not in KINDS:
        problems.append(f"app.kind must be one of {', '.join(KINDS)}")
    if app.get("kind") == "web-shell":
        if not app.get("web_dir"):
            problems.append("web-shell needs app.web_dir (a built bundle with index.html)")
        elif os.path.isdir(app["web_dir"]) and not os.path.isfile(os.path.join(app["web_dir"], "index.html")):
            problems.append(f"app.web_dir has no index.html: {app['web_dir']}")
        if app.get("deeplink_scheme") and not SCHEME_RE.match(app["deeplink_scheme"]):
            problems.append("app.deeplink_scheme must match [a-z][a-z0-9+.-]*")
    if not isinstance(app.get("schema_version"), int) or app["schema_version"] < 0:
        problems.append("app.schema_version must be an int >= 0 (0 = no persisted schema)")
    if doc.get("play", {}).get("track") not in ("internal", "alpha", "beta", "production"):
        problems.append("play.track must be internal|alpha|beta|production")
    for name in ("decisions.md", "UNVERIFIED.md"):
        if not os.path.isfile(os.path.join(out, name)):
            problems.append(f"missing {name}")
    upath = os.path.join(out, "UNVERIFIED.md")
    seen_claims = {}
    if os.path.isfile(upath):
        for n, line in enumerate(open(upath, encoding="utf-8"), 1):
            if line.startswith("- ") and not UNVERIFIED_LINE.match(line.rstrip("\n")):
                problems.append(f"UNVERIFIED.md:{n} must read '- [ ] claim | why | how'")
            elif line.startswith("- "):
                key = claim_key(UNVERIFIED_LINE.match(line.rstrip("\n")).group("claim"))
                if key in seen_claims:
                    problems.append(f"UNVERIFIED.md:{n} repeats the claim on line {seen_claims[key]}")
                else:
                    seen_claims[key] = n
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(prog="contract.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("--out", required=True)
    i.add_argument("--application-id", required=True)
    i.add_argument("--app-name", required=True)
    i.add_argument("--min-sdk", type=int, default=28)
    i.add_argument("--target-sdk", type=int, default=None, help="default: derived from check 140")
    i.add_argument("--kind", choices=KINDS, default="compose")
    i.add_argument("--with-native", action="store_true")
    i.add_argument("--web-dir", default="")
    i.add_argument("--deeplink-scheme", default="")
    i.add_argument("--schema-version", type=int, default=0)
    i.add_argument("--repo", default="", help="owner/name")
    i.add_argument("--play-package", default="")
    i.add_argument("--play-registered", action="store_true")
    i.add_argument("--track", default="internal")
    i.add_argument("--signing-profile", default="")
    i.add_argument("--versions", default="")
    i.add_argument("--check", default="")
    i.add_argument("--unverified", action="append", help="'claim | why | how' (repeatable)")
    i.add_argument("--date", default="")
    v = sub.add_parser("validate"); v.add_argument("dir"); v.add_argument("--date", default=""); v.add_argument("--check", default="")
    s = sub.add_parser("show"); s.add_argument("dir")
    t = sub.add_parser("target-sdk-floor"); t.add_argument("--date", default=""); t.add_argument("--check", default="")
    a = ap.parse_args(argv)
    today = date.fromisoformat(a.date) if getattr(a, "date", "") else datetime.now().date()
    try:
        if a.cmd == "init":
            if not APPLICATION_ID_RE.match(a.application_id):
                raise ValueError(f"invalid applicationId: {a.application_id}")
            if a.min_sdk < 26:
                raise ValueError("minSdk below 26 has no adaptive icons; refuse rather than discover it later")
            doc, unverified = build(a, today)
            write_all(a.out, doc, unverified)
            probs = validate(a.out, today, a.check or None)
            if probs:
                raise ValueError("written, but invalid: " + "; ".join(probs))
            print(f"contract written to {a.out} (targetSdk {doc['app']['target_sdk']}, {len(unverified)} unverified)")
            return 0
        if a.cmd == "validate":
            probs = validate(a.dir, today, a.check or None)
            for p in probs:
                print(f"FAIL {p}")
            if not probs:
                print("ok   contract valid")
            return 1 if probs else 0
        if a.cmd == "show":
            with open(os.path.join(a.dir, "lattice.toml"), "rb") as f:
                print(json.dumps(tomllib.load(f), indent=2))
            return 0
        if a.cmd == "target-sdk-floor":
            check = a.check or find_check_140()
            if not check:
                raise ValueError("check 140 not found; pass --check")
            print(target_sdk_floor(parse_requirements(check), today))
            return 0
    except (ValueError, OSError) as e:
        print(f"contract: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
