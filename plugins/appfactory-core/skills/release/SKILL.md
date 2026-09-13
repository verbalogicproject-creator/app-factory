---
name: release
description: Drives a tagged release of an appfactory-generated app and reports what is actually proven — tag → CI verify job → signed APK + AAB + mapping on a GitHub Release with the certificate digest checked against the pin → Play internal-track upload via Gradle Play Publisher → install from Play on the phone → the on-screen SHA equals the tag. Use for every version that will reach a device that is not the author's; never for feature work.
allowed-tools: Bash, Read, Grep, Glob, AskUserQuestion
---

# Release

Release authority stays with a human. This skill makes the evidence legible; it does not
decide that an app is ready, and it never touches the production track.

## Before the tag

1. `bash scripts/local-build.sh release` is green and its receipt's `tree.sha` is `HEAD`
   with `dirty: false`. A release from an unreceipted tree is a guess.
2. `.appfactory/release/cert.sha256` is committed and equals the vault key's digest
   (`pass_manager.py verify-apk --pin` on any previously published APK proves the pin,
   not the file).
3. Secrets have arrived: `pass_manager.py canary --repo <owner/name>` prints PASS for
   `APPFACTORY_CANARY` and for `PLAY_SERVICE_ACCOUNT_JSON` if Play upload is intended.
   `gh secret list` proves only that a *name* exists.
4. **First release of a new package:** the Play API cannot create an app. Upload one AAB
   by hand in Play Console, invite the service account to the app, and set the repo
   variable `PLAY_RELEASE_STATUS=draft` for this first tag. Record it in
   `.appfactory/contract/UNVERIFIED.md` until done.

## Tag

```bash
git tag -a v0.1.0 -m "v0.1.0" && git push origin v0.1.0
gh run list --commit $(git rev-parse HEAD)      # FULL sha; a short one returns nothing, silently
gh run watch <id>
```

`release.yml` then, in order: preflight → unit tests + lint → decode the keystore →
`assembleRelease bundleRelease` → `verify-apk.sh` (the artifact, not the step) →
certificate digest vs `cert.sha256` (refuses to publish on mismatch or a missing pin) →
GitHub Release with `<slug>-<tag>.apk`, `.aab`, `mapping-<tag>.txt`, `SHA256SUMS.txt` →
`publishBundle --track internal` **only if** `PLAY_SERVICE_ACCOUNT_JSON` is set → scrub
the keystore.

## After the run

- Download the published APK and check it yourself: `python3 .appfactory/bin/apk_cert.py
  <apk>` must print the pinned digest. The runner's green is not your evidence.
- Install from the Play internal-testing link (or sideload the Release APK) on the phone.
  The on-screen build line must show the tag's commit; `git rev-parse <tag>^{}` is the
  comparison.
- Upgrade continuity: a device that had the previous version installed must accept this
  one. `INSTALL_FAILED_UPDATE_INCOMPATIBLE` means signing drift and the cohort is orphaned;
  `INSTALL_FAILED_VERSION_DOWNGRADE` means the versionCode went backwards. Name the cause
  Android gave, never a guess.
- Write the Play release id and the Release URL into `.appfactory/receipts/` next to the
  local receipt. A tag without those two lines is not a release yet.

## What local evidence cannot prove

That the AAB Play serves matches the APK you tested (Play re-signs with its own key only
if you enrolled in Play App Signing — check the Console), that the app launches on API
levels you do not own (the emulator workflow answers that, weekly and on tags), and that
R8 kept what no test touches. Say so in the report rather than rounding "green" up to
"released".

## Operational notes

- Choose a signing-key alias that appears nowhere in your source; GitHub masks the
  secret's value as a substring in every log line, including package paths.
- `gh run list --commit` needs the 40-character SHA. `--limit 1` races the push and can
  report the previous commit's run.
- Third-party actions that receive a credential are pinned to a full commit SHA in the
  workflow (`docs/SECRETS.md`); do not "upgrade" one by editing the tag.
