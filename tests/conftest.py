"""Shared fixtures for hook tests.

Hooks are invoked as `python3 <script>` with a JSON payload on stdin
(see plugins/appfactory-core/hooks/hooks.json). Exit 0 allows, exit 2
blocks with the reason on stderr.
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "appfactory-core"
HOOKS = PLUGIN / "hooks"
RUNTIME_BIN = PLUGIN / "runtime" / "bin"


def load_module(name: str, path: Path):
    """Import a standalone script (not a package) by path, under `name`.

    The runtime/bin/*.py scripts are invoked as scripts, not imported as a
    package, so there is nothing on sys.path to `import` them normally.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_hook(script_name: str, payload: dict) -> tuple[int, str, str]:
    """Run a hook script with `payload` as its stdin JSON.

    Returns (returncode, stdout, stderr).
    """
    script = HOOKS / script_name
    proc = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.returncode, proc.stdout, proc.stderr


@pytest.fixture
def git_repo(tmp_path):
    """Factory fixture: create a git-initialised dir, optionally with a
    scripts/preflight.sh stub that exits with a given code and prints
    given output on stderr.

    Usage: git_repo("name") or git_repo("name", preflight_exit=1, preflight_output="FAIL x")
    """

    def _make(name: str = "repo", preflight_exit: int | None = None, preflight_output: str = ""):
        repo_dir = tmp_path / name
        repo_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init", "-q"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )
        if preflight_exit is not None:
            scripts_dir = repo_dir / "scripts"
            scripts_dir.mkdir(exist_ok=True)
            preflight = scripts_dir / "preflight.sh"
            body = "#!/bin/bash\n"
            if preflight_output:
                body += f'echo "{preflight_output}" >&2\n'
            body += f"exit {preflight_exit}\n"
            preflight.write_text(body)
            preflight.chmod(0o755)
        return repo_dir

    return _make


def _self_signed_der() -> bytes:
    """A throwaway self-signed X.509 cert, DER-encoded, for signing-block fixtures."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "appfactory-test")]
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.DER)


@pytest.fixture(scope="session")
def self_signed_der() -> bytes:
    """Session-scoped: RSA keygen is the slow part of this fixture, reuse it."""
    return _self_signed_der()


@pytest.fixture(scope="session")
def self_signed_der2() -> bytes:
    """A second, distinct cert, for tests that need two different certs at once."""
    return _self_signed_der()
