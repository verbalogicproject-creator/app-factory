---
name: bootstrap
description: Stands up a new Android app repo for the appfactory pipeline and drives it all the way to a signed APK launching on a real phone, before any feature code exists. Fixes the three irreversible decisions, generates and vaults the release signing key, vendors the self-testing preflight corpus and CI workflows, and pushes repository secrets while PROVING they arrived. This skill should be used whenever starting a new Android app, and whenever adopting an existing Android repo that has never produced a verified signed release. Always run this before writing any feature code.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion
---

# Bootstrap an Android app

Take a project from nothing to a signed APK running on the user's phone, with no
local Android SDK. Feature code comes afterwards, never before.

## Why the order is load-bearing

The walking skeleton traverses the whole pipeline first, deliberately. After that,
every failure is attributable to app code rather than to the pipeline — which halves
the diagnostic search space for the rest of the project's life. Building features
first defers the first end-to-end signal until after the most expensive stage, which
is how a predecessor project shipped eleven green builds of an app that crashed
before rendering a pixel.

## Step 1 — Settle the irreversible decisions FIRST

Exactly three things about an Android app can never change after the first user
installs it. Ask about these before anything else, and say why they are permanent:

| Decision | Consequence of changing it |
|---|---|
| `applicationId` | a different app entirely; every existing install is orphaned |
| signing certificate | no installed device will ever accept an update. No recovery. |
| persisted schema version | v2 must migrate from v1 or destroy user data |

Use `AskUserQuestion` for the app name, `applicationId`, GitHub repo name, and
`minSdk`/`targetSdk`. Recommend `minSdk 28` (adaptive icons need 26; 28 avoids PNG
fallbacks entirely) and `targetSdk 34`.

Anything guessed rather than confirmed goes into `.appfactory/contract/UNVERIFIED.md`
and stays flagged until a human confirms it.

## Step 2 — Generate the skeleton

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/runtime/bin/scaffold.py" <target-dir> \
    --application-id <id> --app-name "<name>" --min-sdk 28 --target-sdk 34
```

It refuses an invalid `applicationId` or a `minSdk` below 26 rather than discovering
either later. Then `git init`, and verify locally before pushing anything:

```bash
cd <target-dir> && bash scripts/preflight.sh .
bash scripts/preflight/selftest.sh     # every check detects its own seeded bug
```

Both must be clean. Preflight costs two seconds; a CI round trip costs two to five
minutes.

## Step 3 — Generate and vault the signing key

```bash
python3 .appfactory/bin/pass_manager.py init                 # if no vault yet
python3 .appfactory/bin/pass_manager.py keygen <profile>
```

The keystore is written **into the encrypted vault**, never to a loose `.jks`. The
alias is randomised on purpose: GitHub masks secret *values* as substrings in every
log line, so a common-word alias redacts your own package paths.

Write the printed certificate digest to `.appfactory/release/cert.sha256` and commit
it. It is public information and it is what `release.yml` checks before publishing.

**Then block on backup.** Do not continue until the user confirms the vault exists
somewhere that survives losing this device. Losing the key means every installed
copy of the app can never be updated again — the only failure in this system with no
recovery path whatsoever. Say that plainly; do not soften it.

## Step 4 — Create the repo and PROVE the secrets

Create the GitHub repo, push, then:

```bash
python3 .appfactory/bin/pass_manager.py sync <profile> --repo <owner/name>
python3 .appfactory/bin/pass_manager.py doctor --repo <owner/name>
```

**A present secret name is not a correct secret value.** GitHub never returns a
secret, so `gh secret list` cannot distinguish "set correctly" from "set to the empty
string". That ambiguity once made five consecutive failed attempts look exactly like
success.

The only honest check is the round trip: push a nonce, dispatch `secret-doctor.yml`,
and compare the SHA-256 the runner reports against the local one. Do that before
trusting the signing setup.

Set secrets from this session with non-interactive stdin. Never ask the user to type
one: interactive `gh secret set` fails silently without a TTY.

## Step 5 — Drive it to a launched APK

Push, then watch the run **pinned to the commit**:

```bash
gh run list --commit $(git rev-parse HEAD)
```

The full 40-character SHA. A short one returns an empty list with exit 0 and no
error, which reads as "no run yet" and pushes you back to `--limit 1` — the race that
once reported a fix as verified by a run that never compiled it.

When CI is green, tag `v0.0.1`, let `release.yml` publish, then get the APK to the
phone and have the user install it:

```bash
export TMPDIR=$HOME/.tmp && mkdir -p "$TMPDIR"   # gh defaults to a path absent under PRoot
gh release download v0.0.1 -p "*.apk" -D /tmp/rel
cp /tmp/rel/*.apk /storage/emulated/0/Download/
```

**The skeleton displays its own `versionName`, `versionCode` and git SHA.** Ask the
user to confirm the SHA on screen matches the tagged commit. That single check proves
the artifact in their hand came from the commit you think it did — a screenshot
becomes evidence rather than a vibe.

## Step 6 — Report what is proven and what is not

State plainly which rungs have been exercised and which have not. Do not describe an
unexercised rung as coverage.

Only now begin feature work.

## Failure modes worth naming

- `logcat` returns **silence** in Termux, not an error — no `READ_LOGS`. The app
  reports its own crashes to `Android/data/<pkg>/files/crash.txt`; read it by full
  path, since the parent directory is not listable.
- A green tick on the wrong commit is worse than a red one: it ends the
  investigation. Always confirm `headSha`.
- If a rung has never been observed failing, it is a claim and not a check. Say so.
