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
