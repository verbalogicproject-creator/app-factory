#!/usr/bin/env python3
"""Refuse to write signing material or secrets into the working tree.

WHY THIS IS ABSOLUTE
--------------------
The signing certificate is one of exactly three things about an Android app that can
never be changed after the first user installs it. A release key committed even once
is in the git history forever, and rewriting history does not recall the clones.

Losing control of it is unrecoverable in both directions: leak it and anyone can ship
an "update" to your users; lose it and you can never update them again.

.gitignore is not sufficient. It protects against `git add`, not against a file
landing somewhere it was never expected -- a temp path, a docs folder, a scratch
directory that is not covered by the pattern.

Exit 0 allows, exit 2 blocks.
"""
import fnmatch
import json
import os
import re
import sys

# Filename patterns that are signing material by definition.
BLOCKED_NAMES = [
    "*.jks", "*.keystore", "*.p12", "*.pfx",
    "keystore.properties", "*.pem", "*.key",
    ".env", ".env.*", "*.env",
    "secrets.properties", "google-services.json.real",
]

# Content that is a credential regardless of the filename it lands in.
SECRET_CONTENT = [
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "a Google API key"),
    (re.compile(r"\bghp_[0-9A-Za-z]{36}\b"), "a GitHub personal access token"),
    (re.compile(r"\bgithub_pat_[0-9A-Za-z_]{22,}\b"), "a GitHub fine-grained token"),
    (re.compile(r"\bsk-[0-9A-Za-z]{20,}\b"), "an API secret key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "an AWS access key id"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "a private key"),
]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    if payload.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        return 0

    ti = payload.get("tool_input") or {}
    path = ti.get("file_path", "")
    base = os.path.basename(path)

    for pattern in BLOCKED_NAMES:
        if fnmatch.fnmatch(base, pattern):
            print(
                f"BLOCKED: refusing to write signing material or secrets to {path}\n\n"
                "The signing certificate is one of three things about an Android app that can "
                "NEVER change after the first install. Committed once, it is in the history "
                "forever, and rewriting history does not recall the clones.\n\n"
                "Keep it in the vault:  python3 .appfactory/bin/pass_manager.py set\n"
                "Materialise it only when a build needs it, and shred it after.",
                file=sys.stderr,
            )
            return 2

    body = ti.get("content") or ti.get("new_string") or ""
    for rx, what in SECRET_CONTENT:
        if rx.search(body):
            print(
                f"BLOCKED: the content being written to {path} contains {what}.\n\n"
                "An API key shipped inside an APK is PUBLIC the moment it ships -- strings, jadx "
                "and apktool recover it in seconds, and obfuscation raises that to minutes "
                "without changing the category.\n\n"
                "Either put it behind a backend, or use a key restricted by package name + "
                "signing-certificate fingerprint, which is useless when extracted.",
                file=sys.stderr,
            )
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
