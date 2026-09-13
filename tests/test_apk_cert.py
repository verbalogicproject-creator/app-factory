"""Tests for runtime/bin/apk_cert.py -- SDK-free APK signing cert extraction."""
from __future__ import annotations

import hashlib
import os
import subprocess

import pytest

from tests import apkfixture
from tests.conftest import RUNTIME_BIN, load_module

apk_cert = load_module("apk_cert", RUNTIME_BIN / "apk_cert.py")


@pytest.fixture
def apk_path(tmp_path):
    return tmp_path / "test.apk"


def test_v2_only(apk_path, self_signed_der):
    apkfixture.make_apk(apk_path, {apk_cert.V2_ID: self_signed_der})
    digest, scheme = apk_cert.cert_sha256(str(apk_path))
    assert digest == hashlib.sha256(self_signed_der).hexdigest()
    assert scheme == hex(apk_cert.V2_ID)


def test_v2_and_v3_prefers_v3(apk_path, self_signed_der, self_signed_der2):
    apkfixture.make_apk(
        apk_path,
        {apk_cert.V2_ID: self_signed_der, apk_cert.V3_ID: self_signed_der2},
    )
    digest, scheme = apk_cert.cert_sha256(str(apk_path))
    assert scheme == hex(apk_cert.V3_ID)
    assert digest == hashlib.sha256(self_signed_der2).hexdigest()
    assert digest != hashlib.sha256(self_signed_der).hexdigest()


def test_v31_wins_over_v3_and_v2(apk_path, self_signed_der, self_signed_der2):
    apkfixture.make_apk(
        apk_path,
        {
            apk_cert.V2_ID: self_signed_der,
            apk_cert.V3_ID: self_signed_der,
            apk_cert.V31_ID: self_signed_der2,
        },
    )
    digest, scheme = apk_cert.cert_sha256(str(apk_path))
    assert scheme == hex(apk_cert.V31_ID)
    assert digest == hashlib.sha256(self_signed_der2).hexdigest()


def test_zip_without_signing_block(apk_path):
    apkfixture.make_plain_zip(apk_path)
    with pytest.raises(SystemExit) as excinfo:
        apk_cert.cert_sha256(str(apk_path))
    assert "APK Signing Block" in str(excinfo.value)


def test_not_a_zip_at_all(apk_path):
    apk_path.write_bytes(b"this is not a zip file, just plain bytes" * 50)
    with pytest.raises(SystemExit) as excinfo:
        apk_cert.cert_sha256(str(apk_path))
    assert "EOCD" in str(excinfo.value)


LOCALMIND_APK = os.path.expanduser("~/.appfactory/fixtures/localmind-release.apk")


def _find_apksigner():
    for base in sorted(__import__("glob").glob("/root/android-sdk/build-tools/*")):
        candidate = os.path.join(base, "apksigner")
        if os.path.exists(candidate):
            return candidate
    return None


@pytest.mark.skipif(not os.path.exists(LOCALMIND_APK), reason="no localmind-release.apk fixture")
@pytest.mark.skipif(not _find_apksigner(), reason="no apksigner under /root/android-sdk/build-tools")
def test_matches_apksigner_on_real_apk():
    apksigner = _find_apksigner()
    digest, _scheme = apk_cert.cert_sha256(LOCALMIND_APK)

    r = subprocess.run(
        [apksigner, "verify", "--print-certs", LOCALMIND_APK],
        capture_output=True,
        text=True,
    )
    sha256_line = next(
        line for line in r.stdout.splitlines() if "certificate SHA-256 digest" in line
    )
    apksigner_digest = sha256_line.split(":")[-1].strip().lower()
    assert digest == apksigner_digest
