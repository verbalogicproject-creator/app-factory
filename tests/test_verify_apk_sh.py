"""Tests for runtime/scripts/verify-apk.sh -- post-build APK sanity checks.

AAPT2 is left unset throughout: the environment running this suite is not
guaranteed to have it, and section 2 must SKIP loudly rather than the test
depending on an SDK tool being present.
"""
from __future__ import annotations

import os
import struct
import subprocess
import zipfile

import pytest

from tests.conftest import PLUGIN

VERIFY_APK = PLUGIN / "runtime" / "scripts" / "verify-apk.sh"
FIXTURE_SO = (
    PLUGIN
    / "runtime"
    / "scripts"
    / "preflight"
    / "fixtures"
    / "190-native-libs-resolve"
    / "fixed"
    / "app"
    / "src"
    / "main"
    / "jniLibs"
    / "arm64-v8a"
    / "libmain.so"
)


def _elf64_with_load_align(data: bytes, align: int) -> bytes:
    """Return a copy of an ELF64 .so with every PT_LOAD segment's p_align patched.

    ELF64 program headers start at e_phoff (offset 32, u64 LE), are
    e_phentsize bytes each (offset 54, u16 LE), e_phnum of them (offset 56,
    u16 LE); p_type is the first u32 of each header (PT_LOAD == 1) and
    p_align is the u64 LE at header offset +48.
    """
    buf = bytearray(data)
    e_phoff = struct.unpack_from("<Q", buf, 32)[0]
    e_phentsize = struct.unpack_from("<H", buf, 54)[0]
    e_phnum = struct.unpack_from("<H", buf, 56)[0]
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        p_type = struct.unpack_from("<I", buf, off)[0]
        if p_type == 1:  # PT_LOAD
            struct.pack_into("<Q", buf, off + 48, align)
    return bytes(buf)


@pytest.fixture(scope="module")
def unaligned_so() -> bytes:
    """The real fixture .so, unmodified: LOAD Align 0x1000, below 16 KB."""
    return FIXTURE_SO.read_bytes()


@pytest.fixture(scope="module")
def aligned_so(unaligned_so) -> bytes:
    """Same .so with every PT_LOAD Align patched to 0x4000 (16 KB)."""
    return _elf64_with_load_align(unaligned_so, 0x4000)


def _run(apk_path, *extra_args):
    env = dict(os.environ)
    env.pop("AAPT2", None)
    env.pop("ZIPALIGN", None)
    env.pop("ANDROID_HOME", None)
    env.pop("ANDROID_SDK_ROOT", None)
    return subprocess.run(
        ["bash", str(VERIFY_APK), str(apk_path), *extra_args],
        capture_output=True, text=True, timeout=30, env=env,
    )


def _make_apk(path, so_bytes: bytes | None, *, so_compress=zipfile.ZIP_STORED,
              with_manifest=True, with_arsc=True):
    with zipfile.ZipFile(path, "w") as z:
        if with_manifest:
            z.writestr("AndroidManifest.xml", b"fake manifest, structure not checked here")
        if with_arsc:
            zi = zipfile.ZipInfo("resources.arsc")
            zi.compress_type = zipfile.ZIP_STORED
            z.writestr(zi, b"fake arsc")
        if so_bytes is not None:
            zi = zipfile.ZipInfo("lib/arm64-v8a/libmain.so")
            zi.compress_type = so_compress
            z.writestr(zi, so_bytes)


def test_unaligned_native_lib_fails_with_16kb_message(tmp_path, unaligned_so):
    apk = tmp_path / "bad.apk"
    _make_apk(apk, unaligned_so)
    r = _run(apk)
    assert r.returncode == 1, r.stdout
    assert "16 KB" in r.stdout
    assert "skip" in r.stdout  # aapt2 (and zipalign, since ZIPALIGN is unset) skip loudly


def test_aligned_native_lib_passes(tmp_path, aligned_so):
    apk = tmp_path / "good.apk"
    _make_apk(apk, aligned_so)
    r = _run(apk)
    assert r.returncode == 0, r.stdout
    assert "16 KB" in r.stdout
    assert "skip" in r.stdout


def test_no_native_libs_reports_na_and_passes(tmp_path):
    apk = tmp_path / "nolib.apk"
    _make_apk(apk, None)
    r = _run(apk)
    assert r.returncode == 0, r.stdout
    assert "n/a" in r.stdout


def test_missing_resources_arsc_fails(tmp_path, aligned_so):
    apk = tmp_path / "noarsc.apk"
    _make_apk(apk, aligned_so, with_arsc=False)
    r = _run(apk)
    assert r.returncode == 1, r.stdout
    assert "resources.arsc" in r.stdout


# ---------------------------------------------------------------------------
# Which zipalign. The first CI run (2026-09-17) failed a correctly aligned APK
# because `build-tools/*/zipalign` returned the OLDEST build-tools on the runner,
# whose zipalign has no -P flag.
# ---------------------------------------------------------------------------
OLD_ZIPALIGN = """#!/bin/sh
if [ $# -eq 0 ]; then echo "Usage: zipalign [-f] [-p] [-v] [-z] <align> infile.zip outfile.zip"; echo "  -p: page-align uncompressed .so files"; exit 2; fi
echo "zipalign: unknown option -- P"; exit 2
"""
NEW_ZIPALIGN = """#!/bin/sh
if [ $# -eq 0 ]; then echo "Usage: zipalign -c [-p] [-P <pagesize_kb>] [-v] <align> infile.zip"; exit 2; fi
echo "Verification succesful"; exit 0
"""


def _fake_sdk(tmp_path, versions: dict[str, str]):
    sdk = tmp_path / "sdk"
    for version, body in versions.items():
        d = sdk / "build-tools" / version
        d.mkdir(parents=True)
        (d / "zipalign").write_text(body)
        (d / "zipalign").chmod(0o755)
    return sdk


def _run_with_sdk(apk_path, sdk):
    env = dict(os.environ)
    for k in ("AAPT2", "ZIPALIGN", "ANDROID_SDK_ROOT"):
        env.pop(k, None)
    env["ANDROID_HOME"] = str(sdk)
    # a real zipalign on the host PATH would win over the fake SDK and test nothing
    env["PATH"] = os.pathsep.join(
        d for d in env["PATH"].split(os.pathsep) if not os.path.exists(os.path.join(d, "zipalign"))
    )
    return subprocess.run(["bash", str(VERIFY_APK), str(apk_path)],
                          capture_output=True, text=True, timeout=30, env=env)


def test_newest_build_tools_zipalign_is_used(tmp_path, aligned_so):
    apk = tmp_path / "good.apk"
    _make_apk(apk, aligned_so)
    sdk = _fake_sdk(tmp_path, {"30.0.3": OLD_ZIPALIGN, "36.0.0": NEW_ZIPALIGN})
    r = _run_with_sdk(apk, sdk)
    assert r.returncode == 0, r.stdout
    assert "zipalign -P 16 confirms" in r.stdout


def test_zipalign_without_P_skips_instead_of_failing(tmp_path, aligned_so):
    apk = tmp_path / "good.apk"
    _make_apk(apk, aligned_so)
    sdk = _fake_sdk(tmp_path, {"30.0.3": OLD_ZIPALIGN})
    r = _run_with_sdk(apk, sdk)
    assert r.returncode == 0, r.stdout
    assert "has no -P" in r.stdout


def test_tool_this_host_cannot_execute_skips_instead_of_blaming_the_apk(tmp_path, aligned_so):
    # Third CI run: the SDK's x86_64 aapt2 on an arm64 runner reported
    # "aapt2 cannot parse it: ... Exec format error" -- a host problem filed as an APK defect.
    apk = tmp_path / "good.apk"
    _make_apk(apk, aligned_so)
    foreign = tmp_path / "foreign"
    foreign.write_bytes(b"\x7fELF\x02\x01\x01" + b"\x00" * 9 + b"\x02\x00\x3e\x00" + b"\x00" * 200)
    foreign.chmod(0o755)
    sdk = _fake_sdk(tmp_path, {})
    zipalign_dir = sdk / "build-tools" / "36.0.0"
    zipalign_dir.mkdir(parents=True)
    (zipalign_dir / "zipalign").write_bytes(foreign.read_bytes())
    (zipalign_dir / "zipalign").chmod(0o755)
    env = dict(os.environ)
    for k in ("ZIPALIGN", "ANDROID_SDK_ROOT"):
        env.pop(k, None)
    env["AAPT2"] = str(foreign)
    env["ANDROID_HOME"] = str(sdk)
    env["PATH"] = os.pathsep.join(
        d for d in env["PATH"].split(os.pathsep) if not os.path.exists(os.path.join(d, "zipalign"))
    )
    r = subprocess.run(["bash", str(VERIFY_APK), str(apk)], capture_output=True, text=True, timeout=30, env=env)
    assert r.returncode == 0, r.stdout
    assert "aapt2 at" in r.stdout and "cannot execute on this host" in r.stdout
    assert "zipalign at" in r.stdout and r.stdout.count("cannot execute on this host") == 2
