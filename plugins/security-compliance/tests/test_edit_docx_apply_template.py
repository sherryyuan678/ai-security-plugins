"""Phase D test suite: edit_docx.py --apply-template path.

Uses `from conftest import ...` (no leading dot) per audit fix HIGH 7 —
the tests/ directory has no __init__.py and pytest-collection puts conftest's
parent on sys.path during collection.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (
    assert_content_types_overrides_grafted,
    assert_no_tracked_changes,
    assert_template_grafted,
    assert_word_footer_grafted,
    assert_word_footer_rels_grafted,
    assert_word_header_grafted,
    assert_word_header_rels_grafted,
    assert_word_media_grafted,
    assert_word_numbering_preserved,
    assert_word_styles_grafted,
    assert_word_theme_grafted,
    canonicalize_docx_bytes,
    read_members,
    read_members_binary,
)

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
EDIT_DOCX = HERE.parent / "scripts" / "edit_docx.py"


def _run(target, template, *extra):
    return subprocess.run(
        [
            sys.executable,
            str(EDIT_DOCX),
            "--apply-template",
            str(template),
            str(target),
            *extra,
        ],
        capture_output=True,
        text=True,
    )


def test_happy_path_grafts_template(tmp_path):
    target = tmp_path / "p.docx"
    target.write_bytes((FIXTURES / "plain_summary.docx").read_bytes())
    target_pre = read_members(target)
    template = FIXTURES / "acme_template.docx"

    cp = _run(target, template)
    assert cp.returncode == 0, cp.stderr

    out_members = read_members(target)
    template_members = read_members(template)
    assert_template_grafted(out_members, target_pre, template_members)


def test_target_versions_dir_created(tmp_path):
    target = tmp_path / "p.docx"
    target.write_bytes((FIXTURES / "plain_summary.docx").read_bytes())
    _run(target, FIXTURES / "acme_template.docx")

    versions = list((tmp_path / "p.versions").iterdir())
    assert len(versions) == 1, versions


def test_versioned_filename_pattern_matches_iso_uuid(tmp_path):
    target = tmp_path / "p.docx"
    target.write_bytes((FIXTURES / "plain_summary.docx").read_bytes())
    _run(target, FIXTURES / "acme_template.docx")
    _run(target, FIXTURES / "acme_template.docx")

    pat = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{6}Z-[0-9a-f]{8}\.docx$")
    versions = list((tmp_path / "p.versions").iterdir())
    assert len(versions) == 2, versions
    for f in versions:
        assert pat.match(f.name), f.name


def test_idempotent_double_apply(tmp_path):
    target = tmp_path / "p.docx"
    target.write_bytes((FIXTURES / "plain_summary.docx").read_bytes())
    _run(target, FIXTURES / "acme_template.docx")
    first_canonical = canonicalize_docx_bytes(target.read_bytes())
    _run(target, FIXTURES / "acme_template.docx")
    second_canonical = canonicalize_docx_bytes(target.read_bytes())

    # After canonicalization (stripping dcterms:modified), bytes are equal.
    assert first_canonical == second_canonical


def test_corrupt_template_fails_with_exit_internal(tmp_path):
    target = tmp_path / "p.docx"
    target.write_bytes((FIXTURES / "plain_summary.docx").read_bytes())
    cp = _run(target, FIXTURES / "corrupt_template.docx")
    assert cp.returncode == 3, cp.stderr  # EXIT_INTERNAL


def test_missing_template_fails_with_exit_input(tmp_path):
    target = tmp_path / "p.docx"
    target.write_bytes((FIXTURES / "plain_summary.docx").read_bytes())
    cp = _run(target, tmp_path / "nope.docx")
    assert cp.returncode == 1, cp.stderr  # EXIT_INPUT


def test_unwritable_target_dir_fails_with_exit_write(tmp_path):
    """Audit fix HIGH 8 — EXIT_WRITE=2 is now exercised."""
    if os.geteuid() == 0:
        pytest.skip("running as root; chmod restrictions don't apply")
    target = tmp_path / "p.docx"
    target.write_bytes((FIXTURES / "plain_summary.docx").read_bytes())
    # Make the parent dir read-only so the report.json write fails
    os.chmod(tmp_path, stat.S_IREAD | stat.S_IEXEC)
    try:
        cp = _run(target, FIXTURES / "acme_template.docx")
    finally:
        os.chmod(tmp_path, stat.S_IRWXU)
    assert cp.returncode == 2, cp.stderr  # EXIT_WRITE


def test_promote_failure_restores_prior(tmp_path, monkeypatch):
    """Audit fix HIGH 11 — versioned_promote rollback semantics."""
    sys.path.insert(0, str(EDIT_DOCX.parent))
    import _docx_versions  # type: ignore

    target = tmp_path / "p.docx"
    target.write_bytes(b"OLD CONTENT")
    real_replace = os.replace
    call_count = {"n": 0}

    def flaky_replace(src, dst):
        # Let the first replace (target -> .versions) succeed; fail the second
        # (tempfile -> target) with OSError to trigger rollback.
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise OSError("simulated atomic rename failure")
        return real_replace(src, dst)

    monkeypatch.setattr(_docx_versions.os, "replace", flaky_replace)
    with pytest.raises(OSError):
        _docx_versions.versioned_promote(target, b"NEW CONTENT")
    # Prior should be restored at target
    assert target.exists(), "target missing after rollback"
    assert target.read_bytes() == b"OLD CONTENT"


class TestWordFeatures:
    """Per-Word-feature fidelity assertions (U11).

    Each test isolates one Word component so a regression surfaces to
    exactly one feature in CI logs.
    """

    @pytest.fixture
    def grafted(self, tmp_path):
        target = tmp_path / "p.docx"
        target.write_bytes((FIXTURES / "plain_summary.docx").read_bytes())
        target_pre = read_members(target)
        target_pre_bin = read_members_binary(target)
        template_path = FIXTURES / "acme_template.docx"
        cp = _run(target, template_path)
        assert cp.returncode == 0, cp.stderr
        return {
            "out": read_members(target),
            "out_bin": read_members_binary(target),
            "target_pre": target_pre,
            "target_pre_bin": target_pre_bin,
            "template": read_members(template_path),
            "template_bin": read_members_binary(template_path),
        }

    def test_styles_grafted(self, grafted):
        assert_word_styles_grafted(grafted["out"], grafted["template"])

    def test_theme_grafted(self, grafted):
        assert_word_theme_grafted(grafted["out"], grafted["template"])

    def test_header_grafted(self, grafted):
        assert_word_header_grafted(grafted["out"], grafted["template"])

    def test_header_rels_grafted(self, grafted):
        assert_word_header_rels_grafted(grafted["out"], grafted["template"])

    def test_footer_grafted(self, grafted):
        assert_word_footer_grafted(grafted["out"], grafted["template"])

    def test_footer_rels_grafted(self, grafted):
        assert_word_footer_rels_grafted(grafted["out"], grafted["template"])

    def test_numbering_preserved(self, grafted):
        assert_word_numbering_preserved(grafted["out"], grafted["target_pre"])

    def test_media_grafted(self, grafted):
        assert_word_media_grafted(grafted["out_bin"], grafted["template_bin"])

    def test_content_types_overrides_grafted(self, grafted):
        assert_content_types_overrides_grafted(grafted["out"], grafted["template"])

    def test_no_tracked_changes_in_target_post_graft(self, grafted):
        # apply-template should NOT introduce tracked changes
        assert_no_tracked_changes(grafted["out"])
