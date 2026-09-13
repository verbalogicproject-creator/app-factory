---
name: plan
description: Interviews the user and writes the app contract (.appfactory/contract/) BEFORE any code exists — the irreversible decisions first (applicationId, signing certificate, persisted schema), then app kind, SDK floors derived from the Play requirement table, repo and Play track — with every guess recorded in UNVERIFIED.md. Use this when starting a new Android app, before bootstrap; bootstrap reads the contract instead of re-interviewing.
allowed-tools: Bash, Read, Write, Glob, AskUserQuestion
---

# Plan an app: the contract

Two things about an Android app have **no migration path** after the first install, and a
third is migration-sensitive. They are asked first, and the consequence of changing each is
stated at the point of asking — not discovered later.

| Decision | Consequence of changing it |
|---|---|
| `applicationId` | a different app entirely; every existing install is orphaned |
| signing certificate | no installed device will ever accept an update. No recovery. |
| persisted schema version | v2 must migrate from v1 or destroy user data |

## Interview, in this order

Ask one thing at a time with `AskUserQuestion`; say why each is asked in this position.

1. **App name** (display) — derived: class name and slug; never asked.
2. **`applicationId`** — irreversible. Reverse-DNS, lowercase, at least two segments.
3. **Signing** — a new key generated into the vault (`pass_manager.py keygen <profile>`) or
   an existing keystore imported (`import-keystore`). Until a profile exists, the
   certificate line in the contract is UNVERIFIED.
4. **Persisted data?** If yes: Room, schema version 1 committed with `exportSchema = true`
   (migration-sensitive). If no: `schema_version = 0`.
5. **Kind** — `compose` (native Compose walking skeleton) or `web-shell` (a built web app
   in a WebView with a local command/observe server). For `web-shell`: the path to the
   built bundle (`dist/` with `index.html`) and a deep-link scheme (e.g. `synth`).
6. **Native module** now or later — a `.so` in the APK brings check 150/190 and the 16 KB
   page-alignment rule with it.
7. **minSdk** — recommend 28 (adaptive icons need 26; 28 avoids PNG fallbacks).
8. **targetSdk** — **never asked, derived**: `contract.py target-sdk-floor` reads the dated
   table inside preflight check 140. If the next requirement lands within 120 days it is
   taken now, because an app planned today is submitted later.
9. **GitHub owner/repo** — CI needs it; UNVERIFIED until the repo exists.
10. **Play package + track** — default `internal`. The Play API cannot create an app, so
    the first AAB is uploaded by hand in Play Console; UNVERIFIED until that happened.

## Write it

```bash
python3 .appfactory/bin/contract.py init --out .appfactory/contract \
    --application-id <id> --app-name "<name>" [--kind web-shell --web-dir <dist> --deeplink-scheme <s>] \
    [--schema-version 1] [--repo owner/name] [--signing-profile <p>] [--play-registered] \
    [--unverified "claim | why | how to verify"]...
python3 .appfactory/bin/contract.py validate .appfactory/contract
```

(In the factory repo itself the tool is at `plugins/appfactory-core/runtime/bin/contract.py`.)

`init` writes three files and refuses to leave an invalid contract behind:

- `lattice.toml` — the decisions, machine-readable, plus the adopted version lattice copied
  from `runtime/versions/2026-08-api36.toml` (adopted from android/nowinandroid and
  confirmed by compiling a real app — never derived per-artifact).
- `decisions.md` — the three irreversible rows, values, consequences, date.
- `UNVERIFIED.md` — `- [ ] claim | why unverified | how to verify`. Anything guessed goes
  here and stays flagged until a human ticks it. `validate` rejects malformed lines.

## Hand off

`validate` must print `ok`. Then run `bootstrap`; it reads `.appfactory/contract/lattice.toml`
and does not re-interview. `bootstrap` still works with no contract present, so existing
projects are unaffected.

Do not start feature code. The contract exists so the walking skeleton is built on
decisions that will not move.
