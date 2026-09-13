"""Tests for guard_secret_material.py: refuse to write signing material or secrets.

Includes a regression case for the fixed defect where only the top-level
`content`/`new_string` fields were scanned, so a MultiEdit payload's
`edits[*].new_string` entries -- e.g. edits[1] -- were never inspected.
"""
from tests.conftest import run_hook

SCRIPT = "guard_secret_material.py"

GOOGLE_API_KEY = "AIza" + "a" * 35
GITHUB_PAT = "ghp_" + "a" * 36
RSA_KEY = "-----BEGIN RSA PRIVATE KEY-----\nMIIBogIBAAJ...\n-----END RSA PRIVATE KEY-----"


def _write(file_path: str, content: str = "") -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": file_path, "content": content}}


def _edit(file_path: str, new_string: str) -> dict:
    return {
        "tool_name": "Edit",
        "tool_input": {"file_path": file_path, "old_string": "x", "new_string": new_string},
    }


def _multiedit(file_path: str, new_strings: list[str]) -> dict:
    return {
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_path": file_path,
            "edits": [{"old_string": "x", "new_string": s} for s in new_strings],
        },
    }


def test_tool_not_write_edit_multiedit_allows():
    rc, _, _ = run_hook(SCRIPT, {"tool_name": "Read", "tool_input": {"file_path": "a.jks"}})
    assert rc == 0


def test_write_release_jks_blocks():
    rc, _, err = run_hook(SCRIPT, _write("app/release.jks"))
    assert rc == 2
    assert "BLOCKED" in err


def test_write_keystore_properties_name_blocks():
    rc, _, err = run_hook(SCRIPT, _write("keystore.properties"))
    assert rc == 2
    assert "BLOCKED" in err


def test_write_env_production_blocks():
    rc, _, err = run_hook(SCRIPT, _write(".env.production"))
    assert rc == 2
    assert "BLOCKED" in err


def test_write_pem_extension_blocks():
    rc, _, err = run_hook(SCRIPT, _write("foo.pem"))
    assert rc == 2
    assert "BLOCKED" in err


def test_write_kotlin_content_with_google_api_key_blocks():
    rc, _, err = run_hook(
        SCRIPT, _write("app/src/main/Config.kt", f'val key = "{GOOGLE_API_KEY}"')
    )
    assert rc == 2
    assert "BLOCKED" in err


def test_write_content_with_rsa_private_key_blocks():
    rc, _, err = run_hook(SCRIPT, _write("notes.txt", RSA_KEY))
    assert rc == 2
    assert "BLOCKED" in err


def test_edit_new_string_with_github_pat_blocks():
    rc, _, err = run_hook(SCRIPT, _edit("Config.kt", f'val token = "{GITHUB_PAT}"'))
    assert rc == 2
    assert "BLOCKED" in err


def test_benign_kotlin_allows():
    rc, _, _ = run_hook(
        SCRIPT, _write("app/src/main/Main.kt", "fun main() { println(\"hello\") }")
    )
    assert rc == 0


def test_notes_keystore_md_allows():
    """fnmatch("notes.keystore.md", "*.keystore") is False: fnmatch requires the
    pattern to match the whole basename, and "*.keystore" does not match a name
    that has trailing ".md" after ".keystore". Documented here since the
    filename visually contains 'keystore'."""
    rc, _, _ = run_hook(SCRIPT, _write("notes.keystore.md", "just notes"))
    assert rc == 0


def test_multiedit_second_edit_pem_header_blocks():
    rc, _, err = run_hook(
        SCRIPT,
        _multiedit(
            "Config.kt",
            ["val x = 1", "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----"],
        ),
    )
    assert rc == 2
    assert "BLOCKED" in err


def test_multiedit_only_benign_edits_allows():
    rc, _, _ = run_hook(
        SCRIPT, _multiedit("Config.kt", ["val x = 1", "val y = 2"])
    )
    assert rc == 0


def test_write_service_account_json_name_blocks():
    rc, _, err = run_hook(SCRIPT, _write("keys/my-service-account.json"))
    assert rc == 2
    assert "BLOCKED" in err


def test_write_sa_json_name_blocks():
    rc, _, err = run_hook(SCRIPT, _write("keys/project-sa.json"))
    assert rc == 2
    assert "BLOCKED" in err


def test_write_content_with_private_key_id_blocks():
    rc, _, err = run_hook(
        SCRIPT, _write("config.json", '{"type": "service_account", "private_key_id": "abc"}')
    )
    assert rc == 2
    assert "BLOCKED" in err


def test_blocked_message_says_nothing_ran():
    """A blocked Write runs nothing; and a blocked compound Bash command runs none of
    its parts either. Both surprised someone on 2026-09-13."""
    rc, _, err = run_hook(SCRIPT, {
        "tool_name": "Write",
        "tool_input": {"file_path": "/tmp/release.jks", "content": "x"},
    })
    assert rc == 2
    assert "Nothing in this command ran" in err
