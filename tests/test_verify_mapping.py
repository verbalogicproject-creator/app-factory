"""Tests for runtime/bin/verify_mapping.py -- R8 mapping.txt cross-checks."""
from __future__ import annotations

import textwrap

import pytest

from tests.conftest import RUNTIME_BIN, load_module

verify_mapping = load_module("verify_mapping", RUNTIME_BIN / "verify_mapping.py")

PACKAGE = "com.example.app"

MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="{pkg}">
    <application android:name=".App">
        <activity android:name=".MainActivity" />
    </application>
</manifest>
"""


@pytest.fixture
def manifest_path(tmp_path):
    p = tmp_path / "AndroidManifest.xml"
    p.write_text(MANIFEST.format(pkg=PACKAGE))
    return p


@pytest.fixture
def src_root(tmp_path):
    d = tmp_path / "src"
    d.mkdir()
    return d


def _mapping(tmp_path, text):
    p = tmp_path / "mapping.txt"
    p.write_text(textwrap.dedent(text))
    return p


def _run(mapping_path, manifest_path, src_root, package, *required, capsys):
    argv = [str(mapping_path), str(manifest_path), str(src_root), package, *required]
    monkeypatch_argv = ["verify_mapping.py"] + argv
    import sys

    old_argv = sys.argv
    sys.argv = monkeypatch_argv
    try:
        rc = verify_mapping.main()
    finally:
        sys.argv = old_argv
    out = capsys.readouterr().out
    return rc, out


def test_manifest_classes_kept(tmp_path, manifest_path, src_root, capsys):
    mapping = _mapping(
        tmp_path,
        f"""\
        {PACKAGE}.App -> {PACKAGE}.App:
        {PACKAGE}.MainActivity -> {PACKAGE}.MainActivity:
        """,
    )
    rc, out = _run(mapping, manifest_path, src_root, PACKAGE, capsys=capsys)
    assert rc == 0
    assert "PASS" in out


def test_manifest_class_renamed(tmp_path, manifest_path, src_root, capsys):
    mapping = _mapping(
        tmp_path,
        f"""\
        {PACKAGE}.App -> {PACKAGE}.App:
        {PACKAGE}.MainActivity -> a.b.c:
        """,
    )
    rc, out = _run(mapping, manifest_path, src_root, PACKAGE, capsys=capsys)
    assert rc != 0
    assert "RENAMED" in out


def test_manifest_class_removed(tmp_path, manifest_path, src_root, capsys):
    mapping = _mapping(
        tmp_path,
        f"""\
        {PACKAGE}.App -> {PACKAGE}.App:
        """,
    )
    rc, out = _run(mapping, manifest_path, src_root, PACKAGE, capsys=capsys)
    assert rc != 0
    assert "REMOVED" in out


def test_required_class_absent(tmp_path, manifest_path, src_root, capsys):
    mapping = _mapping(
        tmp_path,
        f"""\
        {PACKAGE}.App -> {PACKAGE}.App:
        {PACKAGE}.MainActivity -> {PACKAGE}.MainActivity:
        """,
    )
    rc, out = _run(
        mapping, manifest_path, src_root, PACKAGE, f"{PACKAGE}.ItemDto", capsys=capsys
    )
    assert rc != 0
    assert "REQUIRED" in out


def test_serializable_field_rename_is_informational(tmp_path, manifest_path, src_root, capsys):
    mapping = _mapping(
        tmp_path,
        f"""\
        {PACKAGE}.App -> {PACKAGE}.App:
        {PACKAGE}.MainActivity -> {PACKAGE}.MainActivity:
        {PACKAGE}.ItemDto -> {PACKAGE}.ItemDto:
            java.lang.String label -> a
        """,
    )
    (src_root / "ItemDto.kt").write_text(
        f"package {PACKAGE}\n\n@Serializable\ndata class ItemDto(val label: String)\n"
    )
    rc, out = _run(mapping, manifest_path, src_root, PACKAGE, capsys=capsys)
    assert rc == 0
    assert "harmless" in out


def test_comments_and_blank_lines_ignored(tmp_path, manifest_path, src_root, capsys):
    mapping = _mapping(
        tmp_path,
        f"""\
        # a comment
        {PACKAGE}.App -> {PACKAGE}.App:

        {PACKAGE}.MainActivity -> {PACKAGE}.MainActivity:
        """,
    )
    rc, out = _run(mapping, manifest_path, src_root, PACKAGE, capsys=capsys)
    assert rc == 0
    assert "PASS" in out
