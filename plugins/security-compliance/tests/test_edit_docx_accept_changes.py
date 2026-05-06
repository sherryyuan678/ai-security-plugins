"""Phase E test suite: edit_docx.py --accept-changes path (in-memory).

After v1.2 runtime audit: soffice CLI does NOT have --accept-changes flag.
Pivoted to in-memory lxml-based accept (the K1 work brought forward).
EXIT_DEPENDENCY now triggers when python-docx is unavailable instead of
when soffice is missing.

Uses `from conftest import ...` (no leading dot) per audit fix HIGH 7.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from conftest import assert_no_tracked_changes, find_tracked_changes, read_members

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
EDIT_DOCX = HERE.parent / "scripts" / "edit_docx.py"


def _run_accept(target):
    return subprocess.run(
        [sys.executable, str(EDIT_DOCX), "--accept-changes", str(target)],
        capture_output=True,
        text=True,
    )


def test_happy_path_strips_tracked_changes(tmp_path):
    """End-to-end: in-memory accept removes <w:ins>/<w:del>/<w:moveFrom>/<w:moveTo>."""
    target = tmp_path / "r.docx"
    target.write_bytes((FIXTURES / "reviewer_marked.docx").read_bytes())

    # Sanity: input HAS tracked changes
    members_pre = read_members(target)
    assert find_tracked_changes(members_pre), "fixture must have tracked changes"

    cp = _run_accept(target)
    assert cp.returncode == 0, cp.stderr

    # Output has NONE
    members_post = read_members(target)
    assert_no_tracked_changes(members_post)


def test_invalid_input_fails_with_exit_input(tmp_path):
    cp = _run_accept(tmp_path / "nope.docx")
    assert cp.returncode == 1, cp.stderr  # EXIT_INPUT


def test_missing_python_docx_fails_with_exit_dependency(tmp_path, monkeypatch):
    """Audit fix HIGH 9 — _resolve_python_docx is monkeypatchable."""
    sys.path.insert(0, str(EDIT_DOCX.parent))
    import edit_docx as ed  # type: ignore

    target = tmp_path / "r.docx"
    target.write_bytes((FIXTURES / "reviewer_marked.docx").read_bytes())

    monkeypatch.setattr(ed, "_resolve_python_docx", lambda: False)

    args = ed._parse_args(["--accept-changes", str(target)])
    rc = ed._run_accept_changes(args)
    assert rc == 4, rc  # EXIT_DEPENDENCY


def test_versioned_promote_creates_versions_dir(tmp_path):
    """Versioned promote semantics work for accept-changes too."""
    target = tmp_path / "r.docx"
    target.write_bytes((FIXTURES / "reviewer_marked.docx").read_bytes())
    cp = _run_accept(target)
    assert cp.returncode == 0, cp.stderr
    versions = list((tmp_path / "r.versions").iterdir())
    assert len(versions) == 1, versions
