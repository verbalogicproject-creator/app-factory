# The limits of preflight

**Rule:** *green preflight is not green CI.* Anything only the CI runner executes
is invisible to a green local run, and a check corpus that pretends otherwise
becomes worse than no corpus, because it stops the investigation early.

## The incident

On 2026-08-15 an audit found `scaffold.py` shipped `gradle-wrapper.properties`
but no `gradlew`, `gradlew.bat`, or `gradle-wrapper.jar`. Every generated app
passed all 14 preflight checks. Every one of them would have died on the first
line of its first CI run, because `ci.yml` calls `./gradlew`.

The bug survived because the check corpus asks "does the source *look* right?"
and no check asked "does the source *run* what the workflows invoke?" Check 100
now grep-extracts `./`-invocations from workflow `run:` blocks and asserts each
is present in the tree. That closes this specific incident. The general
lesson does not close.

## What preflight can and cannot see

Preflight sees:

- File presence, file absence, and cross-reference between them
- Static syntax of build scripts, manifests, workflow YAML, XML resources
- Import and symbol references against declared artifacts
- Placeholders that survived template rendering

Preflight cannot see:

- Anything a compiler catches (Kotlin type errors, Compose runtime,
  KSP/Hilt annotation processing)
- Anything a linker or minifier catches (missing keep rules, R8 stripping)
- Anything the runtime catches (launch crashes, migration failures on device,
  native backend loading)
- Anything the CI environment adds that the local environment lacks (GitHub
  Actions cache, secret injection, runner-specific defaults)

A check must declare its scope and skip loudly when the scope does not apply —
a skipped check that prints nothing is indistinguishable from a passing one.
This is enforced by `lib.sh:af_exit` and the `note()` helper.

## Fixture-first is the mechanism

New checks are written **fixture-first**, and step 2 is the load-bearing one:

1. Write `fixtures/<ID>/bug/` — the smallest tree reproducing the failure.
2. **Run the *existing* preflight against `bug/`. It must PASS.** That proves
   the bug is currently invisible. If it already fails, the check is redundant
   and you have just saved the labour.
3. Write `fixtures/<ID>/fixed/`.
4. Write the check.
5. `selftest.sh` green — including every evasion variant.
6. `README.md` naming the real incident.

`preflight.sh` refuses to run a check with no `bug/` fixture. Not a
convention — the runner refuses. Check `000-checks-have-fixtures` enforces the
existence half on every ordinary run.

## Where CI is the only backstop

Some classes of defect have no preflight shape. For those, the emulator rung
and the release smoke are the earliest signal:

- Launch crashes from missing `@HiltAndroidApp` or a wrong theme reference
  (60, 30 also help pre-launch)
- R8 stripping a class the app references at runtime (behaviour rung: startup
  path exercises the class; a launch smoke catches the crash)
- Migration failures on device with a missing schema asset (130 + the emulator
  migration test)

The rule is: **don't claim a rung catches a defect until the rung has been
observed catching it.** The emulator rung was documented as catching R8
regressions before it was tested, and did not — `testBuildType` silently
defaulted to `debug`, where R8 never runs. Every rung in `docs/VERIFICATION.md`
has been deliberately broken and watched go red.

## Related

- `references/adopt-dont-derive.md` — the higher-level rule preflight is one
  application of
- `docs/CHECKS.md` — the corpus and how to add a check
- `docs/VERIFICATION.md` — the full ladder and how each rung was falsified
