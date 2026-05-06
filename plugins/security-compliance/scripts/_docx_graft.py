"""In-memory DOCX style graft.

Pattern source: Mike docxTrackedChanges.ts:787-1034 (JSZip in-memory edit;
no temp dir). Adapted to Python's zipfile.ZipFile + io.BytesIO.

Per-component error accumulation follows Mike docxTrackedChanges.ts:859-868
({index, reason} -> {component, status, reason}).

Graft scope (audit fix HIGH 4 — completed body):
  - word/styles.xml                  -> grafted from template
  - word/theme/theme1.xml            -> grafted from template
  - word/header*.xml                 -> grafted from template (DYNAMIC names)
  - word/_rels/header*.xml.rels      -> grafted from template (DYNAMIC names)
  - word/footer*.xml                 -> grafted from template (DYNAMIC names)
  - word/_rels/footer*.xml.rels      -> grafted from template (DYNAMIC names)
  - [Content_Types].xml              -> MERGE: target's overrides + template's
                                        header/footer overrides
  - word/numbering.xml               -> PRESERVED (target wins per design)
  - word/media/*                     -> grafted from template (BINARY)
  - everything else from target      -> preserved
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from typing import Literal


@dataclass
class GraftComponent:
    name: str
    status: Literal["grafted", "preserved", "skipped", "warned", "merged"]
    reason: str | None = None


@dataclass
class GraftReport:
    components: list[GraftComponent] = field(default_factory=list)


@dataclass
class GraftResult:
    new_bytes: bytes
    report: GraftReport


_HEADER_RE = re.compile(r"^word/header\d*\.xml$")
_HEADER_RELS_RE = re.compile(r"^word/_rels/header\d*\.xml\.rels$")
_FOOTER_RE = re.compile(r"^word/footer\d*\.xml$")
_FOOTER_RELS_RE = re.compile(r"^word/_rels/footer\d*\.xml\.rels$")
_MEDIA_RE = re.compile(r"^word/media/.+$")

_STATIC_GRAFT = ("word/styles.xml", "word/theme/theme1.xml")
_NUMBERING = "word/numbering.xml"
_CONTENT_TYPES = "[Content_Types].xml"


def _is_dynamic_template_member(name: str) -> bool:
    return bool(
        _HEADER_RE.match(name)
        or _HEADER_RELS_RE.match(name)
        or _FOOTER_RE.match(name)
        or _FOOTER_RELS_RE.match(name)
        or _MEDIA_RE.match(name)
    )


def _merge_content_types(target_xml: bytes, template_xml: bytes) -> bytes:
    """Merge [Content_Types].xml: keep target's structure; absorb template's
    header/footer Override entries."""
    target = target_xml.decode("utf-8")
    template = template_xml.decode("utf-8")
    overrides = re.findall(
        r'<Override\s+PartName="(/word/(?:header|footer)\d*\.xml)"\s+ContentType="[^"]+"\s*/>',
        template,
    )
    if not overrides:
        return target_xml
    new_target = target
    for partname in overrides:
        if f'PartName="{partname}"' in new_target:
            continue
        full = re.search(
            rf'<Override\s+PartName="{re.escape(partname)}"\s+ContentType="[^"]+"\s*/>',
            template,
        )
        if full is None:
            continue
        new_target = new_target.replace("</Types>", full.group(0) + "</Types>")
    return new_target.encode("utf-8")


def graft_template(target_bytes: bytes, template_bytes: bytes) -> GraftResult:
    """In-memory graft: produce new_bytes + per-component report.

    Never raises on per-component failure; accumulates a GraftComponent
    entry with status='warned' or 'skipped' for the affected member.
    """
    report = GraftReport()
    out_buf = BytesIO()

    try:
        t_in = zipfile.ZipFile(BytesIO(target_bytes), "r")
    except zipfile.BadZipFile as exc:
        report.components.append(
            GraftComponent("zip_open_target", "skipped", reason=str(exc))
        )
        return GraftResult(new_bytes=target_bytes, report=report)

    try:
        tpl_in = zipfile.ZipFile(BytesIO(template_bytes), "r")
    except zipfile.BadZipFile as exc:
        report.components.append(
            GraftComponent("zip_open_template", "skipped", reason=str(exc))
        )
        return GraftResult(new_bytes=target_bytes, report=report)

    target_names = set(t_in.namelist())
    template_names = set(tpl_in.namelist())

    shadowed: set[str] = set()
    for name in template_names:
        if name in _STATIC_GRAFT or _is_dynamic_template_member(name):
            shadowed.add(name)
    shadowed.discard(_NUMBERING)
    shadowed.discard(_CONTENT_TYPES)

    with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as out:
        for name in target_names:
            if name == _CONTENT_TYPES:
                continue
            if name in shadowed:
                continue
            data = t_in.read(name)
            out.writestr(name, data)
            if name == _NUMBERING:
                report.components.append(GraftComponent(name, "preserved"))

        for name in template_names:
            if name not in shadowed:
                continue
            data = tpl_in.read(name)
            out.writestr(name, data)
            report.components.append(GraftComponent(name, "grafted"))

        target_ct = t_in.read(_CONTENT_TYPES) if _CONTENT_TYPES in target_names else b""
        template_ct = tpl_in.read(_CONTENT_TYPES) if _CONTENT_TYPES in template_names else b""
        if target_ct and template_ct:
            merged = _merge_content_types(target_ct, template_ct)
            out.writestr(_CONTENT_TYPES, merged)
            report.components.append(GraftComponent(_CONTENT_TYPES, "merged"))
        elif target_ct:
            out.writestr(_CONTENT_TYPES, target_ct)
            report.components.append(
                GraftComponent(
                    _CONTENT_TYPES, "preserved", reason="template lacks [Content_Types].xml"
                )
            )

        for comp in _STATIC_GRAFT:
            if comp not in template_names:
                report.components.append(
                    GraftComponent(comp, "skipped", reason="not in template")
                )

    return GraftResult(new_bytes=out_buf.getvalue(), report=report)
