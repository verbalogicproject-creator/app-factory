---
name: android-dev
description: Turn android-dev mode ON or OFF for this project. While it is on, every Android build in the session goes through the appfactory pipeline — the local ladder, the adopted version lattice, the device install path — without the user restating any of it. Accepts free-text intent, e.g. "/android-dev this is a web app I want an APK from". Use only when the user asks for it by name; never switch the mode on or off on your own initiative.
disable-model-invocation: true
argument-hint: "[on|off|status] or a sentence describing the project"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion
---

# android-dev mode

`$ARGUMENTS` is either a word (`on`, `off`, `status`) or a sentence describing what the
user wants. Empty means `on`.

**Never flip this mode without being asked.** `disable-model-invocation: true` stops the
model selecting this skill on its own; do not work around it by writing the state file
directly for any other reason.

## off / status

`off` — set `enabled: false` in `.claude/appfactory.local.md`, confirm in one line, stop.
`status` — read the state file and the contract, report both in two lines, change nothing.

## on

### 1. Write the state

```bash
mkdir -p .claude
```

Write `.claude/appfactory.local.md`:

```markdown
---
mode: android-dev
enabled: true
activated: <ISO-8601 UTC>
intent: <the user's sentence, verbatim, or "">
---

android-dev mode. Turn off with /appfactory-core:android-dev off
```

Add `.claude/appfactory.local.md` to `.gitignore` if the project has one — it is
machine-local state, like `local.properties`.

The hook reads this file on every prompt from here on. It is live immediately; nothing
needs reloading.

### 2. Establish the shared mental model — once per project

**If `.appfactory/contract/lattice.toml` already exists**, read it, run
`python3 "${CLAUDE_PLUGIN_ROOT}/runtime/bin/contract.py" validate .appfactory/contract`, and report in one
line what the project is: applicationId, kind, targetSdk, and anything still listed in
`UNVERIFIED.md`. Do not re-interview. Go to step 3.

**If there is no contract**, this is the alignment step, and it is the whole reason the
mode has an interview rather than just a switch. Look at the directory first so the
questions are informed rather than generic:

| What you find | What it means |
|---|---|
| `app/build.gradle.kts` or `*.kt` | an existing Android project — adopt, do not scaffold over it |
| `package.json` with a build script, `vite.config.*`, `next.config.*`, `astro.config.*` | a web project — `--kind web-shell`, and it needs a **built** bundle: run `python3 "${CLAUDE_PLUGIN_ROOT}/runtime/bin/webdetect.py" detect <dir>` to name the framework and build command, then `webdetect.py build <dir>` (ask first — it runs the project's install and build) and pass its `webDir` to `scaffold.py --web-dir`. Scaffold into a **sibling** folder (`<web-project>-apk`), never into the web project: Gradle files must not mix with the web source, and scaffolding a non-empty directory needs `--force`, which is the wrong signal. Later bundle updates go through the shell's `scripts/sync-web.sh` |
| neither | a new app — `--kind compose` |

Then run `/appfactory-core:plan`, which owns the interview and writes the contract. Feed
it what the user's `$ARGUMENTS` sentence already told you; do not ask again for anything
they have said. The irreversible decisions come first, and each is asked with its
consequence stated: `applicationId` and the signing certificate have no migration path
after the first install.

Anything guessed goes to `UNVERIFIED.md` and stays flagged.

### 3. Confirm, briefly

One line for what the mode now knows, one line for what it will do without asking, one
for what it will ask about first. Then stop and let the user work. Do not start building.

## How to behave while the mode is on

The doctrine is injected by the hook, so it is already in context. The behavioural rule,
restated because it is the part that is about judgement rather than facts:

- **Act** on the fast rungs when the user's request implies them: preflight, compile,
  unit tests, lint, a debug build, reading a receipt.
- **Ask first** before anything slow or irreversible: installing on the device, a release
  build, a tag, a Play upload, overwriting or adopting an existing project, or anything
  that would take more than a couple of minutes.
- **Report what was proven, not what was run.** A green stage proves what that rung
  proves and nothing more.

When the user's request has genuine forks — which kind, whether to adopt or scaffold,
what the applicationId should be — use `AskUserQuestion` rather than choosing for them.
The mode exists to remove the need to restate the pipeline, not the need to agree on the
project.
