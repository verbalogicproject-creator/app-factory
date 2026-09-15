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

WHICH FIELDS GET SCANNED
-------------------------
The blind spot this hook used to have: content scanning only looked at the
top-level `content` (Write) or `new_string` (Edit) field. A MultiEdit payload
carries `edits: [{old_string, new_string}, ...]`, and a secret sitting in any
edit other than edits[0] -- e.g. edits[1] -- was never scanned. Every edit's
`new_string` is now scanned, not just the top-level fields.

Also widened: Google service-account JSON key files (`*service-account*.json`,
`*-sa.json` by name; `"private_key_id"` by content) are blocked outright --
that JSON blob is a long-lived credential with the same "unrecoverable once
leaked" property as a signing key, not just an Android-signing concern.

Forms this guard still cannot see:
- A secret split across multiple small edits/writes that individually don't
  match a pattern (e.g. half a key per edit, concatenated later).
- A secret that is base64-encoded, rot13'd, string-reversed, or otherwise
  transformed so the literal pattern never appears in the written text.
- A secret written via a tool this hook isn't registered for (e.g. a Bash
  `cat > file <<EOF` heredoc, `curl -o`, or a script the agent invokes that
  writes files itself) -- this hook only fires on Write/Edit/MultiEdit
  tool_input, per hooks.json's matcher.
- A blocked filename pattern matched case-sensitively only; `RELEASE.JKS` on
  a case-sensitive filesystem would not match `*.jks` today.

Exit 0 allows, exit 2 blocks.
"""
import fnmatch
import json
import os
import re
import sys

import cmdparse
import hook_stdin

# Filename patterns that are signing material by definition.
BLOCKED_NAMES = [
    "*.jks", "*.keystore", "*.p12", "*.pfx",
    "keystore.properties", "*.pem", "*.key",
    ".env", ".env.*", "*.env",
    "secrets.properties", "google-services.json.real",
    "*service-account*.json", "*-sa.json",
]

# Content that is a credential regardless of the filename it lands in.
SECRET_CONTENT = [
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "a Google API key"),
    (re.compile(r"\bghp_[0-9A-Za-z]{36}\b"), "a GitHub personal access token"),
    (re.compile(r"\bgithub_pat_[0-9A-Za-z_]{22,}\b"), "a GitHub fine-grained token"),
    (re.compile(r"\bsk-[0-9A-Za-z]{20,}\b"), "an API secret key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "an AWS access key id"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "a private key"),
    (re.compile(r'"private_key_id"'), "a Google service-account JSON key"),
]


def main() -> int:
    try:
        payload = json.loads(hook_stdin.read_stdin_bounded())
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
                "Materialise it only when a build needs it, and shred it after.\n\n"
                + cmdparse.NOTHING_RAN,
                file=sys.stderr,
            )
            return 2

    bodies = [ti.get("content") or "", ti.get("new_string") or ""]
    for edit in ti.get("edits") or []:
        if isinstance(edit, dict):
            bodies.append(edit.get("new_string") or "")

    for body in bodies:
        for rx, what in SECRET_CONTENT:
            if rx.search(body):
                print(
                    f"BLOCKED: the content being written to {path} contains {what}.\n\n"
                    "An API key shipped inside an APK is PUBLIC the moment it ships -- strings, jadx "
                    "and apktool recover it in seconds, and obfuscation raises that to minutes "
                    "without changing the category.\n\n"
                    "Either put it behind a backend, or use a key restricted by package name + "
                    "signing-certificate fingerprint, which is useless when extracted.\n\n"
                    + cmdparse.NOTHING_RAN,
                    file=sys.stderr,
                )
                return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
