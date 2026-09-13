#!/usr/bin/env python3
"""Generate an Android walking skeleton from the appfactory templates.

The mechanical half of bootstrap. Deterministic and testable on its own, so the
skill above it only has to handle decisions — and so `bootstrap reproduces the
conformance repo` is a claim that can actually be diffed.

WHAT A WALKING SKELETON IS FOR
------------------------------
An app that does nothing except launch, be signed, install, and display its own
versionName, versionCode and git SHA. It goes all the way through the pipeline
BEFORE any feature code exists.

That ordering is the point. Afterwards every failure is attributable to app code
rather than to the pipeline, which halves the diagnostic search space for the rest
of the project's life. Building features first defers the first end-to-end signal
until after the most expensive stage.

    scaffold.py <target-dir> --application-id com.example.app --app-name "My App"

KINDS
-----
`compose` (default) is the walking skeleton described above and nothing else.

`web-shell` is the same skeleton PLUS a Compose screen that hosts a built web
bundle in an AndroidX WebView, a Ktor command/observe HTTP server bound to
127.0.0.1, and a foreground service that keeps that server alive. It requires
`--web-dir DIR` pointing at a built bundle (DIR/index.html must exist) --
copied into app/src/main/assets/web/.

HOW A KIND IS LAYERED (read this before adding a third kind)

    templates/app/            the base walking skeleton, always copied first
    templates/kinds/<kind>/   an OVERLAY, same directory shape as templates/app/,
                               copied SECOND and OVERWRITING any base file at the
                               same relative path

Nothing fancier than that. A kind that must replace HomeScreen.kt or the
manifest just ships its own file at that same relative path; copy_app_tree()
does not know or care that it is running twice. The java/ package-nesting
rule (java/Foo.kt -> java/<pkg-path>/Foo.kt, with HomeScreen.kt/Theme.kt
force-nested under ui/) already handles overlay files placed in their own
subdirectory too: java/web/Foo.kt lands at java/<pkg-path>/web/Foo.kt with no
extra mapping entry needed, because the subdirectory travels along inside the
part of the path after "java/" that the mapping only special-cases for two
bare filenames.

`--contract PATH` reads a lattice.toml (see contract.py) and fills in
--kind / --web-dir / --deeplink-scheme / --with-native / --application-id /
--app-name / --min-sdk / --target-sdk for any of those NOT given explicitly
on the command line -- an explicit flag always wins over the contract. When
given, `.appfactory/contract/*` (lattice.toml, decisions.md, UNVERIFIED.md)
is copied into the scaffolded project so the decisions travel with the code.

--with-native is accepted and stored ({{WITH_NATIVE}} = "true"/"false" in
every rendered file) but otherwise inert here -- a later lane implements what
it turns on.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
RUNTIME = os.path.dirname(HERE)
TEMPLATES = os.path.join(RUNTIME, "templates")
KINDS_DIR = os.path.join(TEMPLATES, "kinds")

APPLICATION_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*$")
KINDS = ("compose", "web-shell")
DEFAULT_SAG_PORT = 8765

G, R, Y, DIM, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def ok(m): print(f"{G}ok{OFF}   {m}")
def die(m): sys.exit(f"{R}ERROR{OFF} {m}")
def note(m): print(f"{DIM}     {m}{OFF}")


def substitutions(
    application_id: str,
    app_name: str,
    kind: str = "compose",
    deeplink_scheme: str = "",
    sag_port: int = DEFAULT_SAG_PORT,
    with_native: bool = False,
) -> dict[str, str]:
    # The class name derives from the app name, not the package, so it stays
    # readable when the package is a reverse domain.
    app_class = "".join(w.capitalize() for w in re.split(r"[^A-Za-z0-9]+", app_name) if w) or "App"
    slug = re.sub(r"[^a-z0-9]+", "-", app_name.lower()).strip("-") or "app"
    is_web_shell = kind == "web-shell"
    # web-shell dependency/buildConfig lines are substituted into the BASE
    # app.build.gradle.kts rather than shipped as an overlay copy of that whole
    # file, so the two kinds never carry two independently-drifting copies of
    # everything else in it (signing, R8, Play publishing...). Empty string for
    # compose: the placeholder line then renders to a blank line, which is the
    # one and only difference `--kind compose` output has from before this kind
    # existed at all.
    web_shell_dependencies = (
        "    implementation(libs.androidx.webkit)\n"
        "    implementation(libs.ktor.server.core)\n"
        "    implementation(libs.ktor.server.cio)"
    ) if is_web_shell else ""
    web_shell_buildconfig = (
        f'        buildConfigField("int", "SAG_PORT", "{sag_port}")'
    ) if is_web_shell else ""
    return {
        "{{APPLICATION_ID}}": application_id,
        "{{APP_CLASS}}": app_class,
        "{{APP_NAME}}": app_name,
        "{{APP_NAME_UPPER}}": app_name.upper(),
        "{{APP_SLUG}}": slug,
        "{{PROJECT_NAME}}": app_class,
        "{{APP_TAGLINE}}": "walking skeleton",
        "{{KIND}}": kind,
        "{{DEEPLINK_SCHEME}}": deeplink_scheme or slug,
        "{{SAG_PORT}}": str(sag_port),
        "{{WITH_NATIVE}}": "true" if with_native else "false",
        "{{WEB_SHELL_DEPENDENCIES}}": web_shell_dependencies,
        "{{WEB_SHELL_BUILDCONFIG}}": web_shell_buildconfig,
    }


def render(text: str, subs: dict[str, str]) -> str:
    for k, v in subs.items():
        text = text.replace(k, v)
    return text


# Copied byte-for-byte, never rendered, because for these the BYTES are the artifact
# and none of them contains a placeholder.
#
# Detecting them by catching UnicodeDecodeError is not enough, in both directions:
#
#   gradle-wrapper.jar   a binary that happened to decode as UTF-8 would be pushed
#                        through render() and silently corrupted, and a corrupt
#                        wrapper jar fails as a class-not-found error naming nothing
#   gradlew.bat          decodes fine, and that is the problem. Python's text mode
#                        normalises its CRLF line endings to LF on the way through,
#                        and cmd.exe mis-parses goto/labels in an LF-only batch file.
#                        Measured: 2918 bytes in, 2826 bytes out.
VERBATIM = {"gradle-wrapper.jar", "gradlew", "gradlew.bat"}

# Files the runner executes directly. open(dst, "w") creates mode 644, git records
# the mode, and the runner then says "Permission denied" on the first build line.
# shutil.copy2 already carries the template's mode; this is the belt to that braces,
# because a template whose own +x was lost would reintroduce the bug invisibly.
EXECUTABLE = {"gradlew"}


def copy_rendered(src: str, dst: str, subs: dict[str, str]) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    name = os.path.basename(src)
    if name in VERBATIM:
        shutil.copy2(src, dst)
    else:
        try:
            body = open(src, encoding="utf-8").read()
        except UnicodeDecodeError:
            shutil.copy2(src, dst)
        else:
            open(dst, "w", encoding="utf-8").write(render(body, subs))
    if name in EXECUTABLE:
        os.chmod(dst, 0o755)


def load_contract(path: str) -> dict:
    """Read a lattice.toml's [app] table. Missing keys simply are not in the dict --
    callers fill defaults, exactly as argparse defaults would."""
    with open(path, "rb") as f:
        doc = tomllib.load(f)
    return doc.get("app", {})


def copy_app_tree(app_tpl: str, target: str, pkg_path: str, subs: dict[str, str]) -> int:
    """Copy one template tree shaped like templates/app/ into the scaffolded
    project, applying the java/ package-nesting rule. Used twice: once for the
    base skeleton, once (as an overlay) for a kind's templates/kinds/<kind>/
    tree -- the second call overwrites any base file at the same relative path,
    which is the entire mechanism a kind uses to replace one."""
    count = 0
    for root, _, files in os.walk(app_tpl):
        for f in files:
            src = os.path.join(root, f)
            rel = os.path.relpath(src, app_tpl).replace(os.sep, "/")
            # java/Foo.kt -> java/<pkg path>/Foo.kt, with ui/ and theme/ nesting.
            # A file already inside its own subdirectory under java/ (e.g.
            # java/web/Foo.kt) keeps that subdirectory for free: "name" below is
            # everything after the LAST "/java/", not just the leaf filename.
            if "/java/" in f"/{rel}":
                head, name = rel.rsplit("/java/", 1)
                sub_dir = {"HomeScreen.kt": "ui", "Theme.kt": "ui/theme"}.get(name, "")
                rel = os.path.join(head, "java", pkg_path, sub_dir, name)
            copy_rendered(src, os.path.join(target, "app", rel), subs)
            count += 1
    return count


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("target")
    ap.add_argument("--application-id")
    ap.add_argument("--app-name")
    ap.add_argument("--min-sdk", type=int, default=None)
    ap.add_argument("--target-sdk", type=int, default=None)
    ap.add_argument("--kind", choices=KINDS, default=None)
    ap.add_argument("--web-dir", default=None, help="a built web bundle; DIR/index.html required for --kind web-shell")
    ap.add_argument("--deeplink-scheme", default=None)
    ap.add_argument("--with-native", action="store_true", default=None,
                     help="accepted and stored ({{WITH_NATIVE}}); a later lane implements it")
    ap.add_argument("--contract", default=None, help="a directory containing lattice.toml (see contract.py); "
                     "fills any flag above not given explicitly, and is copied into the scaffolded project")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    # --contract fills anything the command line left unset. Explicit flags always
    # win -- this is what lets a caller override one decision from an otherwise-good
    # contract without editing the file.
    contract_app: dict = {}
    if args.contract:
        lattice_path = os.path.join(args.contract, "lattice.toml") \
            if os.path.isdir(args.contract) else args.contract
        if not os.path.isfile(lattice_path):
            die(f"--contract {args.contract}: no lattice.toml found there")
        contract_app = load_contract(lattice_path)

    def pick(flag_val, key, default=None):
        if flag_val is not None:
            return flag_val
        if key in contract_app and contract_app[key] not in (None, ""):
            return contract_app[key]
        return default

    app_id = pick(args.application_id, "application_id")
    app_name = pick(args.app_name, "app_name")
    if not app_id:
        die("--application-id is required (directly, or via --contract)")
    if not app_name:
        die("--app-name is required (directly, or via --contract)")
    min_sdk = pick(args.min_sdk, "min_sdk", 28)
    target_sdk = pick(args.target_sdk, "target_sdk", 36)
    kind = pick(args.kind, "kind", "compose")
    web_dir = pick(args.web_dir, "web_dir")
    deeplink_scheme = pick(args.deeplink_scheme, "deeplink_scheme", "")
    with_native = bool(pick(args.with_native, "with_native", False))

    if kind not in KINDS:
        die(f"--kind must be one of {', '.join(KINDS)}, got {kind!r}")
    if deeplink_scheme and not SCHEME_RE.match(deeplink_scheme):
        die(f"--deeplink-scheme {deeplink_scheme!r} must match [a-z][a-z0-9+.-]*")

    # applicationId is one of exactly three things that can never change after the
    # first install. Validate it here rather than discover it at upload time.
    if not APPLICATION_ID_RE.match(app_id):
        die(f"applicationId '{app_id}' is not a valid Android package name.\n"
            "       Needs at least two lowercase segments, e.g. com.example.myapp.\n"
            "       It can NEVER be changed after the first user installs.")
    if min_sdk < 26:
        die(f"minSdk {min_sdk} < 26: adaptive icons need 26, and the templates "
            "ship no PNG fallbacks.")

    if kind == "web-shell":
        if not web_dir:
            die("--kind web-shell requires --web-dir DIR (a built web bundle)")
        if not os.path.isfile(os.path.join(web_dir, "index.html")):
            die(f"--web-dir {web_dir} has no index.html -- point it at a BUILT bundle, not source")

    target = os.path.abspath(args.target)
    if os.path.exists(target) and os.listdir(target) and not args.force:
        die(f"{target} exists and is not empty. Use --force to scaffold into it anyway.")

    subs = substitutions(
        app_id, app_name,
        kind=kind,
        deeplink_scheme=deeplink_scheme,
        sag_port=DEFAULT_SAG_PORT,
        with_native=with_native,
    )
    subs["{{MIN_SDK}}"] = str(min_sdk)
    subs["{{TARGET_SDK}}"] = str(target_sdk)
    pkg_path = app_id.replace(".", "/")

    print(f"scaffolding {app_name} ({kind})")
    note(f"applicationId  {app_id}   (IRREVERSIBLE)")
    note(f"class          {subs['{{APP_CLASS}}']}")
    note(f"minSdk/target  {min_sdk}/{target_sdk}")
    if kind == "web-shell":
        note(f"web bundle     {web_dir}")
        note(f"deeplink       {subs['{{DEEPLINK_SCHEME}}']}://")
    print()

    # --- gradle ------------------------------------------------------------
    gradle = os.path.join(TEMPLATES, "gradle")
    mapping = {
        "app.build.gradle.kts": "app/build.gradle.kts",
        "root.build.gradle.kts": "build.gradle.kts",
        "settings.gradle.kts": "settings.gradle.kts",
        "gradle.properties": "gradle.properties",
        "libs.versions.toml": "gradle/libs.versions.toml",
        "proguard-rules.pro": "app/proguard-rules.pro",
        "proguard-test-rules.pro": "app/proguard-test-rules.pro",
        "gitignore": ".gitignore",
        # THE GRADLE WRAPPER IS FOUR FILES, AND ALL FOUR MUST BE COMMITTED.
        #
        # The wrapper pins the Gradle version, and AGP has a hard floor on it. An
        # earlier version of this list shipped only the .properties file, so every
        # generated app declared a Gradle version it had no way to launch: all three
        # of its workflows call ./gradlew, and the very first line of the very first
        # build died with "./gradlew: No such file or directory".
        #
        # It passed the entire preflight corpus on the way out, because a green local
        # run says nothing about a file only the runner ever executes. Check 100 now
        # reads ./-invocations out of workflow run: blocks specifically so this cannot
        # ship again -- including the two quieter variants, a gradlew that is present
        # but mode 644, and a gradlew with no jar beside it.
        "gradlew": "gradlew",
        "gradlew.bat": "gradlew.bat",
        "gradle-wrapper.jar": "gradle/wrapper/gradle-wrapper.jar",
        "gradle-wrapper.properties": "gradle/wrapper/gradle-wrapper.properties",
    }
    for src_name, dst_rel in mapping.items():
        src = os.path.join(gradle, src_name)
        if os.path.exists(src):
            copy_rendered(src, os.path.join(target, dst_rel), subs)
    ok(f"gradle files ({len(mapping)})")

    # --- app sources, into the real package directory ----------------------
    app_tpl = os.path.join(TEMPLATES, "app")
    count = copy_app_tree(app_tpl, target, pkg_path, subs)
    ok(f"app sources ({count})")

    # --- kind overlay --------------------------------------------------------
    # Same tree shape as templates/app/, copied SECOND so it overwrites any base
    # file at the same relative path. See the module docstring ("HOW A KIND IS
    # LAYERED") for why no separate merge logic exists.
    # Kind directories are named exactly as the --kind value (web-shell), and are
    # shaped exactly like templates/app/ itself (an "app/" subdirectory, same
    # src/main, src/androidTest, src/test layout) -- copy_app_tree's relative-path
    # math assumes its app_tpl argument IS that shape, so the overlay's own app/
    # subdirectory is what gets walked, not the kind directory itself.
    kind_app_tpl = os.path.join(KINDS_DIR, kind, "app") if kind != "compose" else None
    if kind_app_tpl and os.path.isdir(kind_app_tpl):
        overlay_count = copy_app_tree(kind_app_tpl, target, pkg_path, subs)
        ok(f"{kind} overlay ({overlay_count} files, overwriting base where they collide)")
    elif kind != "compose":
        die(f"--kind {kind} has no overlay at {kind_app_tpl}")

    # --- web bundle, for web-shell only --------------------------------------
    if kind == "web-shell":
        assets_web = os.path.join(target, "app", "src", "main", "assets", "web")
        if os.path.isdir(assets_web):
            shutil.rmtree(assets_web)
        shutil.copytree(web_dir, assets_web)
        n = sum(len(files) for _, _, files in os.walk(assets_web))
        ok(f"web bundle copied to app/src/main/assets/web/ ({n} files)")

    # --- contract, if one was given ------------------------------------------
    if args.contract:
        contract_src = args.contract if os.path.isdir(args.contract) and \
            os.path.isfile(os.path.join(args.contract, "lattice.toml")) else os.path.dirname(lattice_path)
        contract_dst = os.path.join(target, ".appfactory", "contract")
        os.makedirs(contract_dst, exist_ok=True)
        for name in os.listdir(contract_src):
            s = os.path.join(contract_src, name)
            if os.path.isfile(s):
                shutil.copy2(s, os.path.join(contract_dst, name))
        ok(".appfactory/contract/ copied from --contract")

    # --- vendored runtime --------------------------------------------------
    #
    # scripts/ must be RENDERED, not copied. emulator-verify.sh contains
    # {{APPLICATION_ID}}, and copying it verbatim produced
    #     Error: Activity class {{{APPLICATION_ID}}/...MainActivity} does not exist
    # on the emulator — the launch smoke caught it honestly, but only after a
    # 10-minute run, and only because that rung exists at all.
    #
    # The fixture trees under scripts/preflight/fixtures/ are copied verbatim on
    # purpose: they are deliberately-broken sample projects, and rendering them
    # would corrupt the very bugs they encode.
    for sub_dir, dst in (("scripts", "scripts"), ("bin", ".appfactory/bin")):
        src_root = os.path.join(RUNTIME, sub_dir)
        if not os.path.isdir(src_root):
            continue
        for root, dirs, files in os.walk(src_root):
            # __pycache__ is build output of THIS repo's own tooling, never source --
            # vendoring it ships stale, host-specific .pyc files into every generated
            # app for no reason a scaffolded project could ever need.
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in files:
                if f.endswith(".pyc"):
                    continue
                s = os.path.join(root, f)
                rel = os.path.relpath(s, src_root)
                d = os.path.join(target, dst, rel)
                if "preflight/fixtures/" in rel.replace(os.sep, "/"):
                    os.makedirs(os.path.dirname(d), exist_ok=True)
                    shutil.copy2(s, d)
                else:
                    copy_rendered(s, d, subs)
                if f.endswith((".sh", ".py")):
                    os.chmod(d, 0o755)
    for wf in os.listdir(os.path.join(RUNTIME, "workflows")):
        copy_rendered(os.path.join(RUNTIME, "workflows", wf),
                      os.path.join(target, ".github/workflows", wf), subs)
    ok("runtime vendored (preflight + its fixtures, workflows, bin)")

    os.makedirs(os.path.join(target, ".appfactory/release"), exist_ok=True)
    ok(".appfactory/ created")

    print()
    print("NEXT, in order — each step is cheap and the order is load-bearing:")
    note("1. generate the signing key:  pass_manager.py keygen <profile>")
    note("2. write its cert digest to  .appfactory/release/cert.sha256")
    note("3. push and PROVE the secrets (a present name is not a correct value)")
    note("4. push, watch CI, then tag v0.0.1 and install it on the phone")
    print()
    note("Do not add features until the skeleton has launched on a real device.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
