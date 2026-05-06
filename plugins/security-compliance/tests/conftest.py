"""Shared test helpers for the security-compliance plugin.

pytest auto-loads ``conftest.py`` for fixtures/plugins. The functions below
are also importable as ``from conftest import …`` because pytest puts each
``conftest.py``'s parent directory on ``sys.path`` during collection in the
current pytest setup. If the import ever breaks across pytest configs,
convert these to ``@pytest.fixture`` instead.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path


def read_members(path: Path) -> dict[str, str]:
    """Return ``{member_name: utf-8 contents}`` for every XML member in a docx."""
    out: dict[str, str] = {}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.endswith(".xml") or name.endswith(".rels"):
                out[name] = zf.read(name).decode("utf-8")
    return out


def find_footer_xml(members: dict[str, str]) -> str:
    """Return the concatenated text of every ``word/footer*.xml`` member."""
    return "\n".join(v for k, v in members.items() if k.startswith("word/footer"))


def read_members_binary(path: Path) -> dict[str, bytes]:
    """Return ``{member_name: raw bytes}`` for EVERY member in a docx.

    Audit fix HIGH 6 — read_members only returns .xml/.rels strings; this
    helper returns bytes for every member so per-Word-feature media tests
    can compare binary content (PNG, JPEG, etc.).
    """
    out: dict[str, bytes] = {}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            out[name] = zf.read(name)
    return out


def find_tracked_changes(members: dict) -> list[str]:
    """Scan word/document.xml for tracked-change tag names.

    Members may be {str:str} or {str:bytes}.
    """
    body = members.get("word/document.xml", "")
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    found = []
    for tag in ("w:ins", "w:del", "w:moveFrom", "w:moveTo"):
        if f"<{tag}" in body:
            found.append(tag)
    return found


def assert_no_tracked_changes(members: dict) -> None:
    found = find_tracked_changes(members)
    assert not found, f"unexpected tracked changes: {found}"


_DCTERMS_RE = re.compile(rb"<dcterms:modified[^>]*>[^<]*</dcterms:modified>")


def canonicalize_docx_bytes(b: bytes) -> bytes:
    """Strip dcterms:modified AND normalize zip timestamps so docx bytes
    are deterministic across runs.

    Audit fix HIGH 10. Operates on word/document.xml + docProps/core.xml
    plus every member's mtime stamp in the zip wrapper.
    """
    src = zipfile.ZipFile(io.BytesIO(b), "r")
    out_buf = io.BytesIO()
    with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as out:
        # Iterate in sorted order so member order is also deterministic.
        for name in sorted(src.namelist()):
            data = src.read(name)
            if name in ("word/document.xml", "docProps/core.xml"):
                data = _DCTERMS_RE.sub(
                    b'<dcterms:modified xsi:type="dcterms:W3CDTF">CANONICAL</dcterms:modified>',
                    data,
                )
            # Normalize zip timestamp to the ZIP epoch (1980-01-01 00:00:00)
            zi = zipfile.ZipInfo(filename=name, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            out.writestr(zi, data)
    return out_buf.getvalue()


def assert_word_styles_grafted(out: dict, template: dict) -> None:
    assert out.get("word/styles.xml") == template.get("word/styles.xml"), (
        "word/styles.xml not bytes-equal to template's"
    )


def assert_word_theme_grafted(out: dict, template: dict) -> None:
    assert out.get("word/theme/theme1.xml") == template.get("word/theme/theme1.xml"), (
        "word/theme/theme1.xml not bytes-equal to template's"
    )


def assert_word_header_grafted(out: dict, template: dict) -> None:
    tpl_headers = {
        k: v for k, v in template.items() if re.match(r"^word/header\d*\.xml$", k)
    }
    assert tpl_headers, "template has no headers — fixture bug?"
    for k, v in tpl_headers.items():
        assert out.get(k) == v, f"header drift: {k}"


def assert_word_header_rels_grafted(out: dict, template: dict) -> None:
    tpl_rels = {
        k: v
        for k, v in template.items()
        if re.match(r"^word/_rels/header\d*\.xml\.rels$", k)
    }
    for k, v in tpl_rels.items():
        assert out.get(k) == v, f"header rels drift: {k}"


def assert_word_footer_grafted(out: dict, template: dict) -> None:
    tpl_footers = {
        k: v for k, v in template.items() if re.match(r"^word/footer\d*\.xml$", k)
    }
    assert tpl_footers, "template has no footers — fixture bug?"
    for k, v in tpl_footers.items():
        assert out.get(k) == v, f"footer drift: {k}"


def assert_word_footer_rels_grafted(out: dict, template: dict) -> None:
    tpl_rels = {
        k: v
        for k, v in template.items()
        if re.match(r"^word/_rels/footer\d*\.xml\.rels$", k)
    }
    for k, v in tpl_rels.items():
        assert out.get(k) == v, f"footer rels drift: {k}"


def assert_word_numbering_preserved(out: dict, target_pre: dict) -> None:
    if "word/numbering.xml" in target_pre:
        assert out.get("word/numbering.xml") == target_pre["word/numbering.xml"], (
            "word/numbering.xml not preserved (target's should win)"
        )


def assert_word_media_grafted(out_bin: dict, template_bin: dict) -> None:
    """Audit fix HIGH 6 — operates on read_members_binary output (bytes)."""
    tpl_media = {k: v for k, v in template_bin.items() if k.startswith("word/media/")}
    for k, v in tpl_media.items():
        assert out_bin.get(k) == v, f"media drift: {k}"


def assert_content_types_overrides_grafted(out: dict, template: dict) -> None:
    """Every Override PartName from template that points at a header/footer
    must appear in out's [Content_Types].xml."""
    tpl_ct = template.get("[Content_Types].xml", "")
    out_ct = out.get("[Content_Types].xml", "")
    if isinstance(tpl_ct, bytes):
        tpl_ct = tpl_ct.decode("utf-8", errors="replace")
    if isinstance(out_ct, bytes):
        out_ct = out_ct.decode("utf-8", errors="replace")
    overrides = re.findall(r'PartName="(/word/(?:header|footer)\d*\.xml)"', tpl_ct)
    for ov in overrides:
        assert f'PartName="{ov}"' in out_ct, (
            f"Content_Types override missing for {ov}"
        )


def assert_template_grafted(out: dict, target_pre: dict, template: dict) -> None:
    """Composite: every per-feature assertion in one call."""
    assert_word_styles_grafted(out, template)
    assert_word_theme_grafted(out, template)
    assert_word_header_grafted(out, template)
    assert_word_header_rels_grafted(out, template)
    assert_word_footer_grafted(out, template)
    assert_word_footer_rels_grafted(out, template)
    assert_word_numbering_preserved(out, target_pre)
    assert_content_types_overrides_grafted(out, template)
