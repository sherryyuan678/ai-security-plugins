"""Unit tests for ``scripts/build_docx_summary.py``.

DOCX is a zip file. Body text lives in ``word/document.xml``; footer text
lives in ``word/footer*.xml``. Assertions target the right member.
"""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from conftest import find_footer_xml, read_members

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
BUILDER = PLUGIN_ROOT / "scripts" / "build_docx_summary.py"
FIXTURE = PLUGIN_ROOT / "tests" / "fixtures" / "spot-check-sample.md"


def run_builder(src: Path, dst: Path) -> subprocess.CompletedProcess:
    """Invoke the builder via the same interface ``commands/spot-check.md`` uses."""
    return subprocess.run(
        [sys.executable, str(BUILDER), "--in", str(src), "--out", str(dst)],
        capture_output=True,
        text=True,
        check=False,
    )


def write_md(tmp_path: Path, *, fm: str, body: str) -> Path:
    """Compose a markdown report from front matter + body and write it."""
    src = tmp_path / "report.md"
    src.write_text(f"---\n{fm}\n---\n{body}\n", encoding="utf-8")
    return src


VALID_FM = (
    "type: compliance-spot-check\n"
    "date: 2026-05-06\n"
    'scenario: "Test scenario for unit tests"\n'
    "applicable_frameworks:\n"
    "  - GDPR\n"
    "  - SOC2\n"
    'industry: "fintech"\n'
)


def test_happy_path_produces_valid_docx_with_footer(tmp_path: Path) -> None:
    """Builder writes a valid docx; body + footer assertions target right members."""
    out = tmp_path / "out.docx"
    proc = run_builder(FIXTURE, out)
    assert proc.returncode == 0, proc.stderr
    assert zipfile.is_zipfile(out)

    members = read_members(out)
    doc_xml = members["word/document.xml"]
    footer_xml = find_footer_xml(members)

    assert "Fintech app handling EU customer payment data" in doc_xml
    for framework in ("SOC 2", "GDPR", "PCI DSS", "EU AI Act"):
        assert framework in doc_xml, f"missing display name {framework}"
    assert "Key Findings" in doc_xml
    assert "Priority Actions" in doc_xml

    assert "Confidential — for internal use" in footer_xml
    assert "PAGE" in footer_xml


def test_missing_applicable_frameworks_exits_1(tmp_path: Path) -> None:
    """Front matter missing the applicable_frameworks key → exit 1."""
    fm_no_fw = 'date: 2026-05-06\nscenario: "x"\nindustry: "fintech"\n'
    src = write_md(tmp_path, fm=fm_no_fw, body="# body\n")
    out = tmp_path / "out.docx"
    proc = run_builder(src, out)
    assert proc.returncode == 1, proc.stderr
    assert "applicable_frameworks" in proc.stderr


def test_missing_front_matter_delimiters_exits_1(tmp_path: Path) -> None:
    """No leading ``---`` → exit 1 with a clear message."""
    src = tmp_path / "report.md"
    src.write_text("# Just a title\n\nSome body.\n", encoding="utf-8")
    out = tmp_path / "out.docx"
    proc = run_builder(src, out)
    assert proc.returncode == 1
    assert "front-matter" in proc.stderr.lower() or "delimiter" in proc.stderr.lower()


def test_applicable_frameworks_not_a_list_exits_1(tmp_path: Path) -> None:
    """``applicable_frameworks`` as a scalar → exit 1."""
    fm_scalar = (
        "date: 2026-05-06\n"
        'scenario: "x"\n'
        'applicable_frameworks: "GDPR"\n'
        'industry: "fintech"\n'
    )
    src = write_md(tmp_path, fm=fm_scalar, body="# body\n")
    out = tmp_path / "out.docx"
    proc = run_builder(src, out)
    assert proc.returncode == 1
    assert "list" in proc.stderr.lower() or "applicable_frameworks" in proc.stderr


@pytest.mark.parametrize("missing_field", ["date", "scenario", "industry"])
def test_empty_required_scalar_field_exits_1(
    tmp_path: Path, missing_field: str
) -> None:
    """Empty ``date`` / ``scenario`` / ``industry`` → exit 1."""
    fields = {
        "date": "2026-05-06",
        "scenario": '"x"',
        "industry": '"fintech"',
    }
    fields[missing_field] = '""'
    fm = (
        f"date: {fields['date']}\n"
        f"scenario: {fields['scenario']}\n"
        "applicable_frameworks:\n  - GDPR\n"
        f"industry: {fields['industry']}\n"
    )
    src = write_md(tmp_path, fm=fm, body="# body\n")
    out = tmp_path / "out.docx"
    proc = run_builder(src, out)
    assert proc.returncode == 1, proc.stderr
    assert missing_field in proc.stderr


def test_empty_findings_section_still_writes_valid_docx(tmp_path: Path) -> None:
    """Empty findings → still produces a valid docx with the Findings header."""
    body = "## Compliance Gap Summary\n\n## Recommended Next Steps\n\n1. Action one.\n"
    src = write_md(tmp_path, fm=VALID_FM, body=body)
    out = tmp_path / "out.docx"
    proc = run_builder(src, out)
    assert proc.returncode == 0, proc.stderr
    members = read_members(out)
    assert "Key Findings" in members["word/document.xml"]


def test_long_findings_truncated_to_five(tmp_path: Path) -> None:
    """8 finding sentences → unzipped doc shows exactly 5 numbered items."""
    findings_para = " ".join(f"Finding sentence {i}." for i in range(1, 9))
    body = (
        "## Compliance Gap Summary\n\n"
        f"{findings_para}\n\n"
        "## Recommended Next Steps\n\n"
        "1. Action one.\n2. Action two.\n3. Action three.\n4. Action four.\n"
    )
    src = write_md(tmp_path, fm=VALID_FM, body=body)
    out = tmp_path / "out.docx"
    proc = run_builder(src, out)
    assert proc.returncode == 0, proc.stderr
    members = read_members(out)
    doc_xml = members["word/document.xml"]
    finding_lines = re.findall(r"\b[1-9]\.\s+Finding sentence", doc_xml)
    assert len(finding_lines) == 5, finding_lines


def test_tldr_fallback_when_gap_summary_is_short(tmp_path: Path) -> None:
    """Single-sentence Compliance Gap Summary → top up findings from TL;DR bullets."""
    body = (
        "## TL;DR\n\n"
        "- Bullet alpha.\n- Bullet beta.\n- Bullet gamma.\n\n"
        "## Compliance Gap Summary\n\n"
        "One short sentence.\n\n"
        "## Recommended Next Steps\n\n1. Single action.\n"
    )
    src = write_md(tmp_path, fm=VALID_FM, body=body)
    out = tmp_path / "out.docx"
    proc = run_builder(src, out)
    assert proc.returncode == 0, proc.stderr
    members = read_members(out)
    doc_xml = members["word/document.xml"]
    assert "One short sentence." in doc_xml
    assert "Bullet alpha" in doc_xml
    assert "Bullet beta" in doc_xml


def test_scalar_key_block_list_bypass_rejected(tmp_path: Path) -> None:
    """Block-list value in a scalar position (`date:\\n  - x`) → exit 1."""
    fm_block = (
        "date:\n  - 2026-05-06\n"
        'scenario: "x"\n'
        "applicable_frameworks:\n  - GDPR\n"
        'industry: "fintech"\n'
    )
    src = write_md(tmp_path, fm=fm_block, body="# body\n")
    out = tmp_path / "out.docx"
    proc = run_builder(src, out)
    assert proc.returncode == 1, proc.stderr
    assert "string scalar" in proc.stderr


def test_crlf_line_endings_accepted(tmp_path: Path) -> None:
    """CRLF input parses identically to LF input."""
    src = tmp_path / "report.md"
    src.write_bytes(
        b"---\r\n"
        b"date: 2026-05-06\r\n"
        b'scenario: "Windows-edited report"\r\n'
        b"applicable_frameworks:\r\n  - GDPR\r\n"
        b'industry: "fintech"\r\n'
        b"---\r\n"
        b"## TL;DR\r\n- a\r\n- b\r\n- c\r\n"
    )
    out = tmp_path / "out.docx"
    proc = run_builder(src, out)
    assert proc.returncode == 0, proc.stderr
    members = read_members(out)
    assert "Windows-edited report" in members["word/document.xml"]


def test_utf8_bom_consumed_silently(tmp_path: Path) -> None:
    """UTF-8 BOM at file start does not break the front-matter delimiter check."""
    src = tmp_path / "report.md"
    body = "## TL;DR\n- a\n- b\n- c\n"
    src.write_bytes(b"\xef\xbb\xbf" + (f"---\n{VALID_FM}---\n{body}").encode("utf-8"))
    out = tmp_path / "out.docx"
    proc = run_builder(src, out)
    assert proc.returncode == 0, proc.stderr


def test_invalid_utf8_input_exits_1(tmp_path: Path) -> None:
    """Invalid UTF-8 bytes → exit 1 (input error), not 2 (write error)."""
    src = tmp_path / "report.md"
    src.write_bytes(b"---\nfoo: \xff\xff\xff\n---\n")
    out = tmp_path / "out.docx"
    proc = run_builder(src, out)
    assert proc.returncode == 1, proc.stderr
    assert "decode" in proc.stderr.lower() or "utf-8" in proc.stderr.lower()


def test_scalar_jurisdictions_rejected(tmp_path: Path) -> None:
    """``jurisdictions: "EU"`` (scalar instead of list) → exit 1."""
    fm = (
        "date: 2026-05-06\n"
        'scenario: "x"\n'
        "applicable_frameworks:\n  - GDPR\n"
        'jurisdictions: "EU"\n'
        'industry: "fintech"\n'
    )
    src = write_md(tmp_path, fm=fm, body="# body\n")
    out = tmp_path / "out.docx"
    proc = run_builder(src, out)
    assert proc.returncode == 1, proc.stderr
    assert "jurisdictions" in proc.stderr


def test_h3_section_headings_are_parsed(tmp_path: Path) -> None:
    """`### Compliance Gap Summary` and `### Recommended Next Steps` parse."""
    body = (
        "## TL;DR\n\n- Bullet alpha.\n- Bullet beta.\n\n"
        "### Compliance Gap Summary\n\n"
        "First finding sentence. Second finding sentence. Third finding sentence.\n\n"
        "### Recommended Next Steps\n\n"
        "1. First action.\n2. Second action.\n"
    )
    src = write_md(tmp_path, fm=VALID_FM, body=body)
    out = tmp_path / "out.docx"
    proc = run_builder(src, out)
    assert proc.returncode == 0, proc.stderr
    members = read_members(out)
    doc_xml = members["word/document.xml"]
    assert "First finding sentence" in doc_xml
    assert "First action" in doc_xml
    assert "Second action" in doc_xml


def test_bullet_action_items_are_parsed(tmp_path: Path) -> None:
    """`- Action.` bullets fall back when no numbered items present."""
    body = (
        "## Compliance Gap Summary\n\n"
        "First. Second. Third.\n\n"
        "## Recommended Next Steps\n\n"
        "- Bullet action one.\n- Bullet action two.\n- Bullet action three.\n"
    )
    src = write_md(tmp_path, fm=VALID_FM, body=body)
    out = tmp_path / "out.docx"
    proc = run_builder(src, out)
    assert proc.returncode == 0, proc.stderr
    doc_xml = read_members(out)["word/document.xml"]
    assert "Bullet action one" in doc_xml
    assert "Bullet action two" in doc_xml
    assert "Bullet action three" in doc_xml


def test_markdown_emphasis_stripped_from_actions(tmp_path: Path) -> None:
    """`**Engineering**: Wire up...` → `Engineering: Wire up...` in the docx."""
    body = (
        "## Compliance Gap Summary\n\n"
        "First. Second. Third.\n\n"
        "## Recommended Next Steps\n\n"
        "1. **Engineering**: Wire up workload identity within 30 days.\n"
    )
    src = write_md(tmp_path, fm=VALID_FM, body=body)
    out = tmp_path / "out.docx"
    proc = run_builder(src, out)
    assert proc.returncode == 0, proc.stderr
    doc_xml = read_members(out)["word/document.xml"]
    assert "Engineering: Wire up" in doc_xml
    assert "**Engineering**" not in doc_xml


def test_action_with_multiple_bold_spans_is_not_garbled(tmp_path: Path) -> None:
    """Two bold spans in one action item must not produce mangled text.

    Regression: the old emphasis-stripping regex matched the closing `**`
    greedily and turned `**A** then **B**` into `A** then : B**`. The
    fail-soft fix returns the original text unchanged when a second
    emphasis span is present.
    """
    body = (
        "## Compliance Gap Summary\n\n"
        "First. Second. Third.\n\n"
        "## Recommended Next Steps\n\n"
        "1. **Engineering**: do X with **vendor Y** within 30 days.\n"
    )
    src = write_md(tmp_path, fm=VALID_FM, body=body)
    out = tmp_path / "out.docx"
    proc = run_builder(src, out)
    assert proc.returncode == 0, proc.stderr
    doc_xml = read_members(out)["word/document.xml"]
    assert "vendor Y" in doc_xml
    assert "** then" not in doc_xml
    assert ": B**" not in doc_xml


def test_table_action_skips_header_and_separator(tmp_path: Path) -> None:
    """A markdown table must skip both the header row and the `|---|` separator."""
    body = (
        "## Compliance Gap Summary\n\n"
        "First. Second. Third.\n\n"
        "## Recommended Next Steps\n\n"
        "| Action | Owner |\n"
        "|--------|-------|\n"
        "| Wire up SSO | Engineering |\n"
        "| Run DPIA | Legal |\n"
        "| Adopt federation | Security |\n"
    )
    src = write_md(tmp_path, fm=VALID_FM, body=body)
    out = tmp_path / "out.docx"
    proc = run_builder(src, out)
    assert proc.returncode == 0, proc.stderr
    doc_xml = read_members(out)["word/document.xml"]
    assert "Wire up SSO" in doc_xml
    assert "Run DPIA" in doc_xml
    assert "Adopt federation" in doc_xml
    action_lines = re.findall(r"\b\d+\.\s+Action\b", doc_xml)
    assert action_lines == [], (
        f"header row should not be emitted as an action: {action_lines}"
    )


def test_exit_internal_constant_and_main_handler_present() -> None:
    """The new EXIT_INTERNAL constant + bare-except handler must be wired in."""
    src = BUILDER.read_text(encoding="utf-8")
    assert "\nEXIT_INTERNAL = 3\n" in src
    assert "sys.exit(EXIT_INTERNAL)" in src


def test_isadirectoryerror_routes_to_exit_input(tmp_path: Path) -> None:
    """Passing a directory as --in raises IsADirectoryError → EXIT_INPUT (1).

    Regression check that the existing OSError-→-EXIT_INPUT path still
    catches IsADirectoryError after the EXIT_INTERNAL addition.
    """
    proc = subprocess.run(
        [
            sys.executable,
            str(BUILDER),
            "--in",
            str(tmp_path),
            "--out",
            str(tmp_path / "out.docx"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1, proc.stderr
    assert "cannot read input" in proc.stderr


def test_long_actions_truncated_to_three(tmp_path: Path) -> None:
    """7 actions → unzipped doc shows exactly 3 numbered actions."""
    actions = "\n".join(f"{i}. Action {i}." for i in range(1, 8))
    body = (
        "## Compliance Gap Summary\n\nOne brief finding.\n\n"
        f"## Recommended Next Steps\n\n{actions}\n"
    )
    src = write_md(tmp_path, fm=VALID_FM, body=body)
    out = tmp_path / "out.docx"
    proc = run_builder(src, out)
    assert proc.returncode == 0, proc.stderr
    members = read_members(out)
    doc_xml = members["word/document.xml"]
    action_lines = re.findall(r"\b[1-9]\.\s+Action \d+\.", doc_xml)
    assert len(action_lines) == 3, action_lines
