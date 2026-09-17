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
                keygen               generate a release keystore into the vault
                import-keystore      adopt an existing loose .jks
                set-file             store a file's contents as a named secret
                sync                 push signing (and set-file) secrets to GitHub, then read back
                doctor               probe every known silent-failure mode
                canary               PROVE a secret's value arrived, not just its name
                verify-apk           SDK-free signature check on the phone
```

Checked against `pass_manager.py --help` on 2026-09-17. An earlier version of this list
named `profile`, `get`/`set`, `materialize`, `shred`, `rotate-passphrase` and `backup`;
none of them exist. Local signing without CI (materialize a keystore for one build, then
shred it) is board item G9, deferred to v1.1.

**Values arrive on stdin only.** Never argv — `ps` exposes it — and never shell
history. A bare invocation prints the usage and exits; it never waits on a prompt.
(An earlier version of this page promised a numbered menu that exits on a missing TTY;
checked 2026-09-17, it does not exist.)

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

## Play service-account flow (runtime secret, not build-time)

Automated Play Store uploads (Gradle Play Publisher) need a Google Cloud service
account's JSON key. It is a credential, not a build-time asset like the keystore, but
it deserves the same "never touches a working tree" discipline:

1. Play Console → **Setup → API access** → link/create a Google Cloud project →
   create a service account there, grant it the Play API role, and download its
   **JSON key**.
2. Vault it without it ever landing as a file in this repo:
   ```
   pass_manager.py set-file <profile> --name PLAY_SERVICE_ACCOUNT_JSON --file sa.json
   ```
3. Push it to GitHub alongside the signing trio:
   ```
   pass_manager.py sync <profile> --repo <owner/name>
   ```
4. Prove the value (not just the name) arrived:
   ```
   pass_manager.py canary --repo <owner/name> --profile <profile>
   ```

`release.yml` (owned by another lane) maps the GitHub secret `PLAY_SERVICE_ACCOUNT_JSON`
onto the environment variable Gradle Play Publisher actually reads,
`ANDROID_PUBLISHER_CREDENTIALS` — the plugin wants the JSON **contents**, not a path.

**Never write the JSON key into any tree**, including a scratch or temp directory
inside this repo. `guard_secret_material` blocks it outright by name
(`*service-account*.json`, `*-sa.json`) and by content (`"private_key_id"`), the same
guard that blocks a loose keystore.

**The first AAB upload for a brand-new package is manual**, done once in Play Console.
The Play Publishing API can create *releases* but cannot create the *app listing*
itself, so there is no way to automate the very first upload — every automated release
after that one works normally.

### Pin policy for actions that touch a credential

Any third-party GitHub Action that receives a credential (a signing key, this
service-account JSON, a publish token) is pinned to a **full commit SHA**, with a
trailing `# vX.Y.Z` comment for humans:

```yaml
- uses: r0adkll/upload-google-play@abcdef0123456789abcdef0123456789abcdef01  # v1.1.3
```

A tag is mutable — its owner can repoint it to different code without changing the
version string you see. A commit SHA cannot be silently swapped underneath you.

First-party actions (`actions/*`) and the maintainers with a strong track record on
this exact axis (`gradle/actions/*`, `reactivecircus/*`) stay on major version tags
(`actions/checkout@v4`) — the credential-handling risk this policy targets does not
apply the same way to Actions' and Google's own published actions.

## The failure this all prevents

An ancestor project exported signing credentials as environment variables from its
release workflow — and had **no `signingConfigs` block at all**, so nothing read them.
It published `app-release-unsigned.apk` to a GitHub Release **with a SHA-256 checksum
beside it**, which made it look verified.

Every divergence here is a fix for one of that project's defects.
