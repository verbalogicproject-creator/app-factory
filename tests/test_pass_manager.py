"""Tests for runtime/bin/pass_manager.py -- the encrypted signing-material vault."""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
from types import SimpleNamespace

import pytest

from tests import apkfixture
from tests.conftest import RUNTIME_BIN, load_module

pm = load_module("pass_manager", RUNTIME_BIN / "pass_manager.py")


@pytest.fixture
def vault(tmp_path, monkeypatch):
    """Point the module's vault location at a scratch dir, outside any repo."""
    vdir = tmp_path / "vaulthome" / ".appfactory"
    monkeypatch.setattr(pm, "VAULT_DIR", str(vdir))
    monkeypatch.setattr(pm, "VAULT_PATH", str(vdir / "vault.json"))
    monkeypatch.setenv("HOME", str(tmp_path / "vaulthome"))
    return pm


def test_save_load_round_trip(vault):
    vault.save_vault({"profiles": {"x": 1}}, "correct horse battery staple")
    payload, pw = vault.load_vault(passphrase="correct horse battery staple")
    assert payload == {"profiles": {"x": 1}}
    assert pw == "correct horse battery staple"


def test_wrong_passphrase_exits(vault):
    vault.save_vault({"profiles": {}}, "the-right-passphrase")
    with pytest.raises(SystemExit):
        vault.load_vault(passphrase="the-wrong-passphrase")


def test_vault_file_mode_0600(vault):
    vault.save_vault({"profiles": {}}, "some-passphrase-123")
    mode = stat.S_IMODE(os.stat(vault.VAULT_PATH).st_mode)
    assert mode == 0o600


def test_no_leftover_temp_files(vault):
    vault.save_vault({"profiles": {}}, "some-passphrase-123")
    vault.save_vault({"profiles": {"a": 1}}, "some-passphrase-123")
    entries = os.listdir(vault.VAULT_DIR)
    assert entries == ["vault.json"]


def test_empty_non_tty_passphrase_exits(vault, monkeypatch):
    monkeypatch.setattr(vault.sys, "stdin", io.StringIO(""))
    with pytest.raises(SystemExit):
        vault.read_passphrase()


def test_vault_inside_git_repo_is_refused(vault, tmp_path, monkeypatch):
    home = tmp_path / "vaulthome"
    home.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=home, check=True, capture_output=True)
    os.makedirs(vault.VAULT_DIR, exist_ok=True)
    with pytest.raises(SystemExit) as excinfo:
        vault.assert_vault_outside_repo()
    assert "REFUSING" in str(excinfo.value)


def test_vault_outside_repo_is_fine(vault):
    # No git init in this tmp_path tree at all: must be silent, no exception.
    vault.assert_vault_outside_repo()


# ---------------------------------------------------------------------------
# cmd_sync: secrets travel via stdin, never argv
# ---------------------------------------------------------------------------
def test_cmd_sync_sends_secrets_via_stdin_never_argv(vault, monkeypatch):
    secret_payload = {
        "profiles": {
            "release": {
                "keystore": {
                    "b64": "totally-secret-base64",
                    "alias": "totally-secret-alias",
                    "store_password": "totally-secret-password",
                }
            }
        }
    }
    monkeypatch.setattr(vault, "load_vault", lambda *a, **k: (secret_payload, "pw"))

    calls = []
    secrets = {"totally-secret-base64", "totally-secret-alias", "totally-secret-password"}

    def fake_run(cmd, input=None, text=None, capture_output=None, **kwargs):
        calls.append((list(cmd), input))
        # None of the actual secret values may appear anywhere in the argv list.
        for token in cmd:
            for secret in secrets:
                assert secret not in token, f"secret leaked into argv: {cmd}"
        if cmd[:3] == ["gh", "secret", "set"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:3] == ["gh", "secret", "list"]:
            names = "\n".join(
                ["SIGNING_KEY_BASE64", "SIGNING_KEY_ALIAS", "SIGNING_KEYSTORE_PASSWORD"]
            )
            return SimpleNamespace(returncode=0, stdout=names, stderr="")
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    monkeypatch.setattr(vault.subprocess, "run", fake_run)

    rc = vault.cmd_sync(SimpleNamespace(profile="release", repo="owner/repo"))
    assert rc == 0

    set_calls = [c for c in calls if c[0][:3] == ["gh", "secret", "set"]]
    assert len(set_calls) == 3
    stdin_values = {input_val for _cmd, input_val in set_calls}
    assert stdin_values == secrets


def test_cmd_sync_readback_mismatch_reports_fail(vault, monkeypatch, capsys):
    secret_payload = {
        "profiles": {
            "release": {
                "keystore": {"b64": "b64val", "alias": "aliasval", "store_password": "pwval"}
            }
        }
    }
    monkeypatch.setattr(vault, "load_vault", lambda *a, **k: (secret_payload, "pw"))

    def fake_run(cmd, input=None, text=None, capture_output=None, **kwargs):
        if cmd[:3] == ["gh", "secret", "set"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:3] == ["gh", "secret", "list"]:
            # SIGNING_KEY_ALIAS never made it back -- a read-back mismatch.
            names = "SIGNING_KEY_BASE64\nSIGNING_KEYSTORE_PASSWORD"
            return SimpleNamespace(returncode=0, stdout=names, stderr="")
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    monkeypatch.setattr(vault.subprocess, "run", fake_run)
    vault.cmd_sync(SimpleNamespace(profile="release", repo="owner/repo"))
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "SIGNING_KEY_ALIAS" in out


# ---------------------------------------------------------------------------
# cmd_verify_apk: pin match / mismatch against the synthetic APK
# ---------------------------------------------------------------------------
def test_cmd_verify_apk_pin_match(tmp_path, self_signed_der):
    apk_path = tmp_path / "app.apk"
    apkfixture.make_apk(apk_path, {0x7109871A: self_signed_der})
    pin_path = tmp_path / "cert.sha256"
    pin_path.write_text(hashlib.sha256(self_signed_der).hexdigest())
    rc = pm.cmd_verify_apk(SimpleNamespace(apk=str(apk_path), pin=str(pin_path)))
    assert rc == 0


def test_cmd_verify_apk_pin_mismatch(tmp_path, self_signed_der):
    apk_path = tmp_path / "app.apk"
    apkfixture.make_apk(apk_path, {0x7109871A: self_signed_der})
    pin_path = tmp_path / "cert.sha256"
    pin_path.write_text("0" * 64)
    rc = pm.cmd_verify_apk(SimpleNamespace(apk=str(apk_path), pin=str(pin_path)))
    assert rc == 1


def test_cmd_verify_apk_no_pin_just_prints(tmp_path, self_signed_der, capsys):
    apk_path = tmp_path / "app.apk"
    apkfixture.make_apk(apk_path, {0x7109871A: self_signed_der})
    rc = pm.cmd_verify_apk(SimpleNamespace(apk=str(apk_path), pin=None))
    assert rc == 0
    assert "apk cert" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# keygen / import-keystore: need a real JDK keytool, and are genuinely slow.
# ---------------------------------------------------------------------------
@pytest.mark.slow
@pytest.mark.skipif(not shutil.which("keytool"), reason="no keytool (JDK) on PATH")
def test_cmd_keygen_round_trip(vault):
    vault.save_vault({"profiles": {}}, "vault-passphrase-123")
    args = SimpleNamespace(
        profile="release",
        alias="myrelkey",
        password="storepass123",
        dname="CN=Test,O=Test,C=US",
        force=False,
    )
    monkeypatch_load = vault.load_vault
    # cmd_keygen calls load_vault() with no passphrase -> would prompt. Feed it via
    # a direct monkeypatch instead of stdin plumbing.
    orig_load_vault = vault.load_vault
    vault.load_vault = lambda *a, **k: orig_load_vault(passphrase="vault-passphrase-123")
    try:
        rc = vault.cmd_keygen(args)
    finally:
        vault.load_vault = monkeypatch_load

    assert rc == 0
    payload, _pw = orig_load_vault(passphrase="vault-passphrase-123")
    ks = payload["profiles"]["release"]["keystore"]
    assert ks["alias"] == "myrelkey"
    assert len(ks["sha256"]) == 64
    assert len(ks["cert_sha256"]) == 64


@pytest.mark.slow
@pytest.mark.skipif(not shutil.which("keytool"), reason="no keytool (JDK) on PATH")
def test_cmd_import_keystore_round_trip(vault, tmp_path):
    ks_path = tmp_path / "loose.jks"
    subprocess.run(
        [
            "keytool", "-genkeypair", "-v", "-keystore", str(ks_path), "-alias", "loosealias",
            "-keyalg", "RSA", "-keysize", "2048", "-validity", "3650",
            "-dname", "CN=Loose,O=Test,C=US", "-storepass", "loosepass123",
            "-keypass", "loosepass123",
        ],
        check=True, capture_output=True,
    )

    vault.save_vault({"profiles": {}}, "vault-passphrase-123")
    orig_load_vault = vault.load_vault
    vault.load_vault = lambda *a, **k: orig_load_vault(passphrase="vault-passphrase-123")
    try:
        args = SimpleNamespace(
            keystore=str(ks_path), password="loosepass123", password_file=None,
            alias=None, profile="imported", force=False,
        )
        rc = vault.cmd_import_keystore(args)
    finally:
        vault.load_vault = orig_load_vault

    assert rc == 0
    payload, _pw = orig_load_vault(passphrase="vault-passphrase-123")
    ks = payload["profiles"]["imported"]["keystore"]
    assert ks["alias"] == "loosealias"
    assert ks["imported_from"] == str(ks_path)


# ---------------------------------------------------------------------------
# set-file: stores {value, sha256, added}; refuses bad names / oversized files
# ---------------------------------------------------------------------------
def test_cmd_set_file_stores_digest_and_value(vault, tmp_path):
    vault.save_vault({"profiles": {}}, "vault-passphrase-123")
    orig_load_vault = vault.load_vault
    vault.load_vault = lambda *a, **k: orig_load_vault(passphrase="vault-passphrase-123")
    try:
        sa_path = tmp_path / "sa.json"
        sa_path.write_text('{"type": "service_account"}')
        args = SimpleNamespace(profile="release", name="PLAY_SERVICE_ACCOUNT_JSON",
                               file=str(sa_path))
        rc = vault.cmd_set_file(args)
    finally:
        vault.load_vault = orig_load_vault

    assert rc == 0
    payload, _pw = orig_load_vault(passphrase="vault-passphrase-123")
    entry = payload["profiles"]["release"]["secrets"]["PLAY_SERVICE_ACCOUNT_JSON"]
    assert entry["value"] == '{"type": "service_account"}'
    assert entry["sha256"] == hashlib.sha256(sa_path.read_bytes()).hexdigest()
    assert "added" in entry


def test_cmd_set_file_never_prints_value(vault, tmp_path, capsys):
    vault.save_vault({"profiles": {}}, "vault-passphrase-123")
    orig_load_vault = vault.load_vault
    vault.load_vault = lambda *a, **k: orig_load_vault(passphrase="vault-passphrase-123")
    try:
        sa_path = tmp_path / "sa.json"
        sa_path.write_text("super-secret-value-xyz")
        args = SimpleNamespace(profile="release", name="MY_SECRET", file=str(sa_path))
        vault.cmd_set_file(args)
    finally:
        vault.load_vault = orig_load_vault
    out = capsys.readouterr().out
    assert "super-secret-value-xyz" not in out


def test_cmd_set_file_refuses_bad_name(vault, tmp_path):
    sa_path = tmp_path / "sa.json"
    sa_path.write_text("x")
    args = SimpleNamespace(profile="release", name="lowercase_bad", file=str(sa_path))
    with pytest.raises(SystemExit):
        vault.cmd_set_file(args)


def test_cmd_set_file_refuses_large_file(vault, tmp_path):
    big_path = tmp_path / "big.json"
    big_path.write_bytes(b"a" * (64 * 1024 + 1))
    args = SimpleNamespace(profile="release", name="TOO_BIG", file=str(big_path))
    with pytest.raises(SystemExit):
        vault.cmd_set_file(args)


# ---------------------------------------------------------------------------
# sync: exit code reflects real success/failure, and pushes set-file secrets too
# ---------------------------------------------------------------------------
def test_cmd_sync_pushes_secrets_and_exits_0_on_success(vault, monkeypatch):
    payload = {
        "profiles": {
            "release": {
                "keystore": {"b64": "b64val", "alias": "aliasval", "store_password": "pwval"},
                "secrets": {
                    "PLAY_SERVICE_ACCOUNT_JSON": {"value": "sa-json-contents", "sha256": "x"},
                },
            }
        }
    }
    monkeypatch.setattr(vault, "load_vault", lambda *a, **k: (payload, "pw"))

    def fake_run(cmd, input=None, text=None, capture_output=None, **kwargs):
        if cmd[:3] == ["gh", "secret", "set"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:3] == ["gh", "secret", "list"]:
            names = "\n".join([
                "SIGNING_KEY_BASE64", "SIGNING_KEY_ALIAS", "SIGNING_KEYSTORE_PASSWORD",
                "PLAY_SERVICE_ACCOUNT_JSON",
            ])
            return SimpleNamespace(returncode=0, stdout=names, stderr="")
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    monkeypatch.setattr(vault.subprocess, "run", fake_run)
    rc = vault.cmd_sync(SimpleNamespace(profile="release", repo="owner/repo"))
    assert rc == 0


def test_cmd_sync_exit_1_when_gh_secret_set_fails(vault, monkeypatch):
    payload = {
        "profiles": {
            "release": {
                "keystore": {"b64": "b64val", "alias": "aliasval", "store_password": "pwval"},
            }
        }
    }
    monkeypatch.setattr(vault, "load_vault", lambda *a, **k: (payload, "pw"))

    def fake_run(cmd, input=None, text=None, capture_output=None, **kwargs):
        if cmd[:3] == ["gh", "secret", "set"]:
            if "SIGNING_KEY_ALIAS" in cmd:
                return SimpleNamespace(returncode=1, stdout="", stderr="boom")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:3] == ["gh", "secret", "list"]:
            names = "SIGNING_KEY_BASE64\nSIGNING_KEYSTORE_PASSWORD"
            return SimpleNamespace(returncode=0, stdout=names, stderr="")
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    monkeypatch.setattr(vault.subprocess, "run", fake_run)
    rc = vault.cmd_sync(SimpleNamespace(profile="release", repo="owner/repo"))
    assert rc == 1


def test_cmd_sync_exit_1_on_missing_readback_name(vault, monkeypatch):
    payload = {
        "profiles": {
            "release": {
                "keystore": {"b64": "b64val", "alias": "aliasval", "store_password": "pwval"},
            }
        }
    }
    monkeypatch.setattr(vault, "load_vault", lambda *a, **k: (payload, "pw"))

    def fake_run(cmd, input=None, text=None, capture_output=None, **kwargs):
        if cmd[:3] == ["gh", "secret", "set"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:3] == ["gh", "secret", "list"]:
            # SIGNING_KEY_ALIAS never made it back -- a read-back mismatch.
            names = "SIGNING_KEY_BASE64\nSIGNING_KEYSTORE_PASSWORD"
            return SimpleNamespace(returncode=0, stdout=names, stderr="")
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    monkeypatch.setattr(vault.subprocess, "run", fake_run)
    rc = vault.cmd_sync(SimpleNamespace(profile="release", repo="owner/repo"))
    assert rc == 1


# ---------------------------------------------------------------------------
# canary: PASS/FAIL against a fake `gh`, and the run-list poll carries --commit
# ---------------------------------------------------------------------------
FAKE_SHA = "a" * 40


def _canary_fake_run_factory(log_text, run_list_json):
    calls = []

    def fake_run(cmd, input=None, text=None, capture_output=None, **kwargs):
        calls.append((list(cmd), input))
        if cmd[:2] == ["git", "rev-parse"]:
            if "--abbrev-ref" in cmd:
                return SimpleNamespace(returncode=0, stdout="main\n", stderr="")
            return SimpleNamespace(returncode=0, stdout=FAKE_SHA + "\n", stderr="")
        if cmd[:3] == ["gh", "secret", "set"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:3] == ["gh", "workflow", "run"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:3] == ["gh", "run", "list"]:
            return SimpleNamespace(returncode=0, stdout=run_list_json, stderr="")
        if cmd[:3] == ["gh", "run", "view"]:
            return SimpleNamespace(returncode=0, stdout=log_text, stderr="")
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    return fake_run, calls


def test_cmd_canary_pass_path(vault, monkeypatch):
    captured_nonce = {}

    def fake_run(cmd, input=None, text=None, capture_output=None, **kwargs):
        if cmd[:3] == ["gh", "secret", "set"] and cmd[3] == "APPFACTORY_CANARY":
            captured_nonce["nonce"] = input
        if cmd[:2] == ["git", "rev-parse"]:
            if "--abbrev-ref" in cmd:
                return SimpleNamespace(returncode=0, stdout="main\n", stderr="")
            return SimpleNamespace(returncode=0, stdout=FAKE_SHA + "\n", stderr="")
        if cmd[:3] == ["gh", "secret", "set"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:3] == ["gh", "workflow", "run"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:3] == ["gh", "run", "list"]:
            runs = [{"databaseId": 123, "status": "completed", "conclusion": "success"}]
            return SimpleNamespace(returncode=0, stdout=json.dumps(runs), stderr="")
        if cmd[:3] == ["gh", "run", "view"]:
            digest = hashlib.sha256(captured_nonce["nonce"].encode()).hexdigest()
            log = f"name=APPFACTORY_CANARY len=64 sha256={digest}\n"
            return SimpleNamespace(returncode=0, stdout=log, stderr="")
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    monkeypatch.setattr(vault.subprocess, "run", fake_run)
    args = SimpleNamespace(repo="owner/repo", profile=None, timeout=1, interval=0.01)
    rc = vault.cmd_canary(args)
    assert rc == 0


def test_cmd_canary_fail_path_digest_mismatch(vault, monkeypatch):
    log = "name=APPFACTORY_CANARY len=64 sha256=" + ("0" * 64) + "\n"
    runs = [{"databaseId": 123, "status": "completed", "conclusion": "success"}]
    fake_run, calls = _canary_fake_run_factory(log, json.dumps(runs))
    monkeypatch.setattr(vault.subprocess, "run", fake_run)

    args = SimpleNamespace(repo="owner/repo", profile=None, timeout=1, interval=0.01)
    rc = vault.cmd_canary(args)
    assert rc == 1

    run_list_calls = [c for c, _ in calls if c[:3] == ["gh", "run", "list"]]
    assert run_list_calls, "expected a `gh run list` call"
    for c in run_list_calls:
        assert "--commit" in c
        commit_value = c[c.index("--commit") + 1]
        assert commit_value == FAKE_SHA
        assert len(commit_value) == 40


def test_cmd_canary_checks_profile_secrets(vault, monkeypatch):
    vault.save_vault({
        "profiles": {
            "release": {
                "secrets": {
                    "PLAY_SERVICE_ACCOUNT_JSON": {
                        "value": "sa-contents",
                        "sha256": hashlib.sha256(b"sa-contents").hexdigest(),
                    }
                }
            }
        }
    }, "vault-passphrase-123")
    orig_load_vault = vault.load_vault
    monkeypatch.setattr(vault, "load_vault", lambda *a, **k: orig_load_vault(passphrase="vault-passphrase-123"))

    captured_nonce = {}

    def fake_run(cmd, input=None, text=None, capture_output=None, **kwargs):
        if cmd[:3] == ["gh", "secret", "set"] and cmd[3] == "APPFACTORY_CANARY":
            captured_nonce["nonce"] = input
        if cmd[:2] == ["git", "rev-parse"]:
            if "--abbrev-ref" in cmd:
                return SimpleNamespace(returncode=0, stdout="main\n", stderr="")
            return SimpleNamespace(returncode=0, stdout=FAKE_SHA + "\n", stderr="")
        if cmd[:3] == ["gh", "secret", "set"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:3] == ["gh", "workflow", "run"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:3] == ["gh", "run", "list"]:
            runs = [{"databaseId": 123, "status": "completed", "conclusion": "success"}]
            return SimpleNamespace(returncode=0, stdout=json.dumps(runs), stderr="")
        if cmd[:3] == ["gh", "run", "view"]:
            canary_digest = hashlib.sha256(captured_nonce["nonce"].encode()).hexdigest()
            sa_digest = hashlib.sha256(b"sa-contents").hexdigest()
            log = (
                f"name=APPFACTORY_CANARY len=64 sha256={canary_digest}\n"
                f"name=PLAY_SERVICE_ACCOUNT_JSON len=11 sha256={sa_digest}\n"
            )
            return SimpleNamespace(returncode=0, stdout=log, stderr="")
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    monkeypatch.setattr(vault.subprocess, "run", fake_run)
    args = SimpleNamespace(repo="owner/repo", profile="release", timeout=1, interval=0.01)
    rc = vault.cmd_canary(args)
    assert rc == 0


# ---------------------------------------------------------------------------
# --passphrase-stdin: reads the passphrase from stdin's first line, bypassing
# getpass even when stdin otherwise looks like a TTY.
# ---------------------------------------------------------------------------
class _FakeTTYStdin(io.StringIO):
    def isatty(self):
        return True


def test_passphrase_stdin_flag_bypasses_getpass(vault, monkeypatch):
    monkeypatch.setattr(vault, "PASSPHRASE_STDIN", True)
    monkeypatch.setattr(vault.sys, "stdin", _FakeTTYStdin("my-passphrase-from-stdin\n"))

    def boom(*a, **k):
        raise AssertionError("getpass should not be called when --passphrase-stdin is set")
    monkeypatch.setattr(vault.getpass, "getpass", boom)

    pw = vault.read_passphrase()
    assert pw == "my-passphrase-from-stdin"


def test_passphrase_stdin_flag_empty_line_exits(vault, monkeypatch):
    monkeypatch.setattr(vault, "PASSPHRASE_STDIN", True)
    monkeypatch.setattr(vault.sys, "stdin", _FakeTTYStdin(""))
    with pytest.raises(SystemExit):
        vault.read_passphrase()
