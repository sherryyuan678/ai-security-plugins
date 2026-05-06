#!/usr/bin/env python3
"""Edit a DOCX in place: apply a template's styling OR accept all tracked changes.

Exit codes (from _docx_versions):
    0 EXIT_OK
    1 EXIT_INPUT       — bad arg, missing file, malformed input
    2 EXIT_WRITE       — fs error promoting output
    3 EXIT_INTERNAL    — graft/validate/parse failure
    4 EXIT_DEPENDENCY  — soffice/python-docx/etc not available
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _docx_versions import (  # noqa: E402
    EXIT_DEPENDENCY,
    EXIT_INPUT,
    EXIT_INTERNAL,
    EXIT_OK,
    EXIT_WRITE,
    versioned_promote,
)
from _docx_validate import validate_edited_docx_bytes  # noqa: E402
from _docx_graft import graft_template  # noqa: E402

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"

ACCEPT_PARTS_PREFIX = ("word/document.xml",)
ACCEPT_PARTS_PATTERNS = (
    "word/header",
    "word/footer",
    "word/footnotes.xml",
    "word/endnotes.xml",
    "word/comments.xml",
)


def _resolve_soffice() -> str | None:
    """Return path to soffice or None. Tests monkeypatch this. (Audit fix HIGH 9.)

    Kept as a top-level injectable resolver. Currently unused by the main
    accept-changes path (which is in-memory) but reserved for future K-items
    that may need a real LibreOffice subprocess (e.g., PDF render).
    """
    p = shutil.which("soffice")
    if p:
        return p
    for cand in (
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/usr/bin/soffice",
        "/opt/homebrew/bin/soffice",
    ):
        if Path(cand).exists():
            return cand
    return None


def _resolve_python_docx() -> bool:
    """Tests monkeypatch this to simulate missing python-docx for EXIT_DEPENDENCY."""
    try:
        import docx  # noqa: F401, PLC0415
        return True
    except ImportError:
        return False


def _accept_changes_inmemory(target_bytes: bytes) -> bytes:
    """Strip tracked-change elements from a docx, in-memory, via lxml.

    Per WordprocessingML spec semantics:
      <w:ins>          -> unwrap (keep inner runs; insertion accepted)
      <w:del>          -> drop entirely (text removed; deletion accepted)
      <w:moveFrom>     -> drop entirely (move's source removed)
      <w:moveTo>       -> unwrap (move's target kept)
      Range markers (<w:moveFromRangeStart/End>, etc.) -> drop entirely

    Applied to: word/document.xml, word/header*.xml, word/footer*.xml,
    word/footnotes.xml, word/endnotes.xml, word/comments.xml when present.
    """
    from lxml import etree  # noqa: PLC0415

    src = zipfile.ZipFile(io.BytesIO(target_bytes), "r")
    out_buf = io.BytesIO()

    drop_tags = {
        f"{W}del",
        f"{W}moveFrom",
        f"{W}moveFromRangeStart",
        f"{W}moveFromRangeEnd",
        f"{W}moveToRangeStart",
        f"{W}moveToRangeEnd",
        f"{W}customXmlInsRangeStart",
        f"{W}customXmlInsRangeEnd",
        f"{W}customXmlDelRangeStart",
        f"{W}customXmlDelRangeEnd",
        f"{W}customXmlMoveFromRangeStart",
        f"{W}customXmlMoveFromRangeEnd",
        f"{W}customXmlMoveToRangeStart",
        f"{W}customXmlMoveToRangeEnd",
        f"{W}cellIns",
        f"{W}cellDel",
        f"{W}cellMerge",
    }
    unwrap_tags = {
        f"{W}ins",
        f"{W}moveTo",
    }

    def is_target(name: str) -> bool:
        if name in ACCEPT_PARTS_PREFIX:
            return True
        return any(name.startswith(p) and name.endswith(".xml") for p in ACCEPT_PARTS_PATTERNS)

    with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as out:
        for name in src.namelist():
            data = src.read(name)
            if is_target(name):
                try:
                    tree = etree.fromstring(data)
                except etree.XMLSyntaxError:
                    out.writestr(name, data)
                    continue
                # Drop elements whose entire subtree is removed
                for el in tree.iter():
                    pass  # placeholder; we modify via parent below
                for el in list(tree.iter()):
                    if el.tag in drop_tags:
                        parent = el.getparent()
                        if parent is not None:
                            parent.remove(el)
                # Unwrap <w:ins>, <w:moveTo>: replace element with its children, preserving tail
                for el in list(tree.iter()):
                    if el.tag in unwrap_tags:
                        parent = el.getparent()
                        if parent is None:
                            continue
                        idx = list(parent).index(el)
                        for i, child in enumerate(list(el)):
                            parent.insert(idx + i, child)
                        if el.tail:
                            # attach tail to the last child or to the parent's previous sibling
                            children = list(el)
                            if children:
                                last = children[-1]
                                last.tail = (last.tail or "") + el.tail
                        parent.remove(el)
                data = etree.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone=True)
            out.writestr(name, data)

    return out_buf.getvalue()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="edit_docx",
        description="Apply a template's styling to a docx OR accept all tracked changes.",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--apply-template", metavar="TEMPLATE_DOCX")
    g.add_argument("--accept-changes", action="store_true")
    p.add_argument("target", help="path to target .docx")
    p.add_argument("--report-out", help="path to write report.json (default: <target>.report.json)")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def _write_report(args: argparse.Namespace, target: Path, report: dict) -> Path:
    report_path = (
        Path(args.report_out)
        if args.report_out
        else target.with_suffix(".docx.report.json")
    )
    report_path.write_text(json.dumps(report, indent=2))
    return report_path


def _run_apply_template(args: argparse.Namespace) -> int:
    target = Path(args.target)
    template = Path(args.apply_template)
    if not target.exists():
        print(f"ERROR: target not found: {target}", file=sys.stderr)
        return EXIT_INPUT
    if not template.exists():
        print(f"ERROR: template not found: {template}", file=sys.stderr)
        return EXIT_INPUT
    if args.dry_run:
        print(f"DRY-RUN: would graft {template} into {target}")
        return EXIT_OK

    target_bytes = target.read_bytes()
    template_bytes = template.read_bytes()
    graft = graft_template(target_bytes, template_bytes)
    val = validate_edited_docx_bytes(graft.new_bytes)
    report = {
        "graft": [c.__dict__ for c in graft.report.components],
        "validate": [s.__dict__ for s in val.stages],
        "ok": val.ok,
    }
    try:
        report_path = _write_report(args, target, report)
    except PermissionError as exc:
        print(f"ERROR: cannot write report: {exc}", file=sys.stderr)
        return EXIT_WRITE

    if not val.ok:
        print(f"ERROR: validation failed; see {report_path}", file=sys.stderr)
        return EXIT_INTERNAL
    try:
        versioned_promote(target, graft.new_bytes)
    except PermissionError as exc:
        print(f"ERROR: write error during promote: {exc}", file=sys.stderr)
        return EXIT_WRITE
    return EXIT_OK


def _run_accept_changes(args: argparse.Namespace) -> int:
    target = Path(args.target)
    if not target.exists():
        print(f"ERROR: target not found: {target}", file=sys.stderr)
        return EXIT_INPUT

    if not _resolve_python_docx():
        print(
            "ERROR: python-docx not installed; cannot validate output",
            file=sys.stderr,
        )
        return EXIT_DEPENDENCY

    if args.dry_run:
        print(f"DRY-RUN: would in-memory-accept-changes {target}")
        return EXIT_OK

    target_bytes = target.read_bytes()
    try:
        new_bytes = _accept_changes_inmemory(target_bytes)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: in-memory accept-changes failed: {exc}", file=sys.stderr)
        return EXIT_INTERNAL

    val = validate_edited_docx_bytes(new_bytes)
    if not val.ok:
        print(f"ERROR: post-accept validation failed: {val.stages}", file=sys.stderr)
        return EXIT_INTERNAL
    try:
        versioned_promote(target, new_bytes)
    except PermissionError as exc:
        print(f"ERROR: write error during promote: {exc}", file=sys.stderr)
        return EXIT_WRITE
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.apply_template:
            return _run_apply_template(args)
        return _run_accept_changes(args)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_INPUT
    except PermissionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_WRITE
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main())
