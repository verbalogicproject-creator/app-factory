"""Tests that the check corpus is self-consistent.

Complements scripts/repo-check.sh's own count assertion by putting the same
claim under `pytest`: the corpus, the selftest, and docs/CHECKS.md must all
agree on how many checks exist.
"""
from __future__ import annotations

import re
import subprocess

import pytest

from tests.conftest import PLUGIN, ROOT

PREFLIGHT = PLUGIN / "runtime" / "scripts" / "preflight"
CHECKS_DIR = PREFLIGHT / "checks"
SELFTEST = PREFLIGHT / "selftest.sh"
CHECKS_DOC = ROOT / "docs" / "CHECKS.md"


def _check_ids():
    return sorted(p.stem for p in CHECKS_DIR.glob("[0-9][0-9][0-9]-*.sh"))


def test_checks_doc_row_count_matches_corpus():
    doc_text = CHECKS_DOC.read_text(encoding="utf-8")
    rows = re.findall(r"^\| \d{3} ", doc_text, flags=re.M)
    assert len(rows) == len(_check_ids())


@pytest.mark.slow
def test_selftest_reports_every_check_verified():
    ids = _check_ids()
    r = subprocess.run(
        ["bash", str(SELFTEST)],
        capture_output=True, text=True, cwd=ROOT, timeout=180,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    # The exact summary line selftest.sh prints on success.
    match = re.search(
        r"Selftest clean.*?-- (\d+) checks each verified against the bug they target\.",
        r.stdout,
    )
    assert match, f"expected summary line not found in:\n{r.stdout}"
    assert int(match.group(1)) == len(ids)
