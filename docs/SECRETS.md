# Secrets

## Two kinds, and the difference matters

**Build-time** — the release keystore. Never enters the APK. Its loss is
**unrecoverable**: you cannot re-key an installed cohort, and there is no support
ticket that fixes it. This is the only failure in the whole pipeline with no remedy at
all, which is why `bootstrap` treats offline backup as a blocking step requiring typed
confirmation, and `doctor` warns until a backup is registered.

**Runtime — and runtime secrets are not secret.** An API key shipped in an APK is
public the moment it ships. `BuildConfig`, `resValue`, NDK-hidden strings and R8 all
merely raise extraction from seconds to minutes. So key-shaped literals **fail the
build** rather than producing a warning.

The sanctioned exception is a key bound to **package name + signing certificate
fingerprint** — Maps, Firebase, Gemini restrictions — which is useless when extracted.
Those are recorded as `apiKeys[].restriction: package+cert` and verified by `doctor`.

This is also where "contract-first API design" earns its real place: not as a universal
second step, but as the **decision procedure for whether you need a backend at all.**
One unrestricted key implies a server, and therefore implies an API contract. Derived,
not mandatory.

## The vault

`~/.appfactory/vault.json`, mode 0600, **outside every git worktree** — and `init` and
`doctor` hard-refuse if the resolved path is inside one. Enforced by filesystem
location, not by `.gitignore`, because `.gitignore` is a request and a location is a
fact.

`cryptography` Fernet with scrypt (`n=2**15, r=8, p=1`), parameters stored in the vault
header so they can be raised later without breaking existing vaults.

The keystore **bytes** live inside the vault. One file to back up, and no `.jks` on
disk between builds.

### Why not gpg

`gpg` drives an agent with TTY-interactive pinentry. An
interactive-prompt-without-a-TTY failure is the exact thing that already cost five
silent attempts here. Rejected on principle, not preference.

`argon2`, `nacl`, `keyring` and `age` are not available on the target device.

## Commands

```
pass_manager.py init                 create the vault
                profile              per-app settings
                keygen               generate a release keystore into the vault
                import-keystore      adopt an existing .jks
                get / set            read and write values
                materialize          write a keystore to a temp path for a build
                shred                remove it again
                sync                 push credentials to GitHub Actions
                canary               PROVE a secret arrived
                doctor               five probes, each naming a distinct cause
                rotate-passphrase
                backup
                verify-apk           SDK-free signature check on the phone
```

**Values arrive on stdin only.** Never argv — `ps` exposes it — and never shell
history. A bare invocation prints a numbered menu and **exits loudly on a missing TTY**
rather than hanging or silently doing nothing.

## The canary, and why it is not optional

Setting a GitHub secret here once failed **five consecutive times with no error
message.** Five apparent successes. Zero secrets set.

The root cause was that interactive `gh secret set` fails silently without a TTY. But
the reason it went undetected for five attempts is more important:

**GitHub never returns a secret value.** `gh secret list` proves that a *name* exists.
It cannot tell you whether the value is correct, or whether it is the empty string.

So `doctor` pushes `APPFACTORY_CANARY=<nonce>`, dispatches a 15-second
`secret-doctor.yml` that prints `sha256($APPFACTORY_CANARY)` to the step summary, and
compares. That round trip is the only honest end-to-end evidence a secret arrived.

### The other four probes

`doctor` runs five independent checks, each of which names a *different* cause, because
the five failures were indistinguishable from the outside:

| Probe | Failure it names |
|---|---|
| TTY | `stdin.isatty()` — every write path uses stdin |
| auth scope | `gh api repos/{o}/{r} --jq .permissions.admin` — secret writes need admin, and a token without it fails looking like nothing happened |
| repo resolution | wrong repo, right command |
| TMPDIR | `gh` defaults to `/data/local/tmp`, absent under PRoot |
| canary | the value actually arrived |

The TMPDIR probe is not theoretical — `gh run download` fails with
`open /data/local/tmp/…: no such file or directory`, which names the path and not the
cause.

## Standing invariants

`doctor` asserts all of these:

- `git log --all -- '*.jks' keystore.properties` is empty
- vault mode is 0600
- the vault's keystore digest matches
- the latest published APK's certificate digest equals the pin in
  `.appfactory/release/cert.sha256`

## The cert pin

`.appfactory/release/cert.sha256` holds the SHA-256 of the signing certificate. It is
**public information and safe to commit** — it is what every installed copy already
carries.

`release.yml` verifies the built APK against it **before publishing**, and that check
was deliberately falsified — a wrong pin produced a correct rejection and nothing was
published — before being trusted.

`apk_cert.py` parses the **APK Signing Block** (v2/v3) directly, stdlib only, no
Android SDK. An earlier version read `META-INF/*.RSA`, which is dead code: modern AGP
signs v2/v3 only, and that path would have silently found nothing.

## The failure this all prevents

An ancestor project exported signing credentials as environment variables from its
release workflow — and had **no `signingConfigs` block at all**, so nothing read them.
It published `app-release-unsigned.apk` to a GitHub Release **with a SHA-256 checksum
beside it**, which made it look verified.

Every divergence here is a fix for one of that project's defects.
