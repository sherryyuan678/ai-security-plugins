"""Three-stage validator for DOCX bytes/files.

Stage 1: ZIP magic-byte check (Mike chatTools.ts:1175-1278 pattern).
Stage 2: XML well-formedness for every .xml/.rels member + required-OPC-member
         check.
Stage 3: parse roundtrip via python-docx Document(path).

Pure Python; no subprocess. (Audit fix HIGH 3 — validate_report.py is a
markdown-spot-check validator, not a DOCX/XML validator.)

Exposed:
    validate_edited_docx(path: str | Path) -> ValidationReport
    validate_edited_docx_bytes(b: bytes) -> ValidationReport

K5: lift this module to a shared library when a second consumer appears.
"""

from __future__ import annotations

import os
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ZIP_MAGIC = b"\x50\x4b\x03\x04"

REQUIRED_OPC_MEMBERS = frozenset(
    {
        "[Content_Types].xml",
        "_rels/.rels",
        "word/document.xml",
    }
)


@dataclass
class ValidationStage:
    name: str
    status: Literal["pass", "fail"]
    reason: str | None = None


@dataclass
class ValidationReport:
    stages: list[ValidationStage] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(s.status == "pass" for s in self.stages)


def _check_zip_signature(path: Path) -> ValidationStage:
    try:
        with open(path, "rb") as f:
            head = f.read(4)
    except OSError as exc:
        return ValidationStage("zip_signature", "fail", reason=f"read error: {exc}")
    if head != ZIP_MAGIC:
        return ValidationStage(
            "zip_signature",
            "fail",
            reason=f"got {head!r}, want {ZIP_MAGIC!r}",
        )
    return ValidationStage("zip_signature", "pass")


def _check_xml_wellformed(path: Path) -> ValidationStage:
    """Walk every .xml/.rels member; assert it parses; assert required OPC parts present."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())
            missing = REQUIRED_OPC_MEMBERS - names
            if missing:
                return ValidationStage(
                    "xml_wellformed",
                    "fail",
                    reason=f"missing required OPC members: {sorted(missing)}",
                )
            for name in names:
                if not (name.endswith(".xml") or name.endswith(".rels")):
                    continue
                data = zf.read(name)
                try:
                    ET.fromstring(data)
                except ET.ParseError as exc:
                    return ValidationStage(
                        "xml_wellformed",
                        "fail",
                        reason=f"{name}: {exc}",
                    )
    except zipfile.BadZipFile as exc:
        return ValidationStage("xml_wellformed", "fail", reason=f"bad zip: {exc}")
    except OSError as exc:
        return ValidationStage("xml_wellformed", "fail", reason=f"read error: {exc}")
    return ValidationStage("xml_wellformed", "pass")


def _check_parse_roundtrip(path: Path) -> ValidationStage:
    try:
        from docx import Document  # noqa: PLC0415
    except ImportError as exc:
        return ValidationStage(
            "parse_roundtrip",
            "fail",
            reason=f"python-docx not installed: {exc}",
        )
    try:
        Document(str(path))
    except Exception as exc:  # noqa: BLE001
        return ValidationStage(
            "parse_roundtrip",
            "fail",
            reason=f"{type(exc).__name__}: {exc}",
        )
    return ValidationStage("parse_roundtrip", "pass")


def validate_edited_docx(path: str | Path) -> ValidationReport:
    """Run all three validation stages on a DOCX file path.

    Raises FileNotFoundError if the path does not exist.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    return ValidationReport(
        stages=[
            _check_zip_signature(p),
            _check_xml_wellformed(p),
            _check_parse_roundtrip(p),
        ]
    )


def validate_edited_docx_bytes(b: bytes) -> ValidationReport:
    """Validate DOCX bytes by writing to a tempfile and validating; cleans up."""
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        f.write(b)
        tmp = Path(f.name)
    try:
        return validate_edited_docx(tmp)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
