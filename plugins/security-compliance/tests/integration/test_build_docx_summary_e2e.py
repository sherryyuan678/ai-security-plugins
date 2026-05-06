"""End-to-end: spot-check markdown report → Python DOCX summary.

Operates entirely on the LOCAL plugin tree. Drives the same
``python3 build_docx_summary.py --in <md> --out <docx>`` interface that
``commands/spot-check.md`` Step B documents.
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


def _run_builder(src: Path, dst: Path) -> subprocess.CompletedProcess:
    """Invoke the builder via the canonical CLI (matches Step B exactly)."""
    return subprocess.run(
        [sys.executable, str(BUILDER), "--in", str(src), "--out", str(dst)],
        capture_output=True,
        text=True,
        check=False,
    )


def _write_report(
    tmp: Path,
    *,
    frameworks: list[str],
    findings_para: str,
    actions: list[str],
) -> Path:
    """Compose a Step-A-shaped markdown report under ``tmp``."""
    fw_block = "\n".join(f"  - {fw}" for fw in frameworks)
    actions_block = "\n".join(
        f"{idx}. {action}" for idx, action in enumerate(actions, 1)
    )
    body = (
        "---\n"
        "type: compliance-spot-check\n"
        "date: 2026-05-06\n"
        'scenario: "Fintech app handling EU customer payment data and AI credit decisions"\n'
        "applicable_frameworks:\n"
        f"{fw_block}\n"
        "jurisdictions:\n"
        "  - EU\n"
        "  - UK\n"
        'industry: "fintech"\n'
        "tags: [compliance, spot-check]\n"
        "---\n"
        "\n"
        "# Compliance Spot-Check\n"
        "\n"
        "## TL;DR\n"
        "\n"
        "- Cap-stone bullet alpha.\n"
        "- Cap-stone bullet beta.\n"
        "\n"
        "## Compliance Gap Summary\n"
        "\n"
        f"{findings_para}\n"
        "\n"
        "## Recommended Next Steps\n"
        "\n"
        f"{actions_block}\n"
    )
    src = tmp / "report.md"
    src.write_text(body, encoding="utf-8")
    return src


@pytest.mark.integration
def test_e2e_happy_path_through_step_b_contract(tmp_path: Path) -> None:
    """Step A markdown → Python builder → valid one-page DOCX with footer."""
    src = _write_report(
        tmp_path,
        frameworks=["GDPR", "PCI_DSS", "EU_AI_ACT", "SOC2"],
        findings_para=(
            "Custom RBAC has no break-glass workflow. JIT credentials are not "
            "used in production. The credit-decision flow lacks a GDPR Article "
            "22 human-in-the-loop override. PCI DSS 4.0.1 password complexity "
            "controls are missing on the admin console. Workload-identity "
            "federation is not in place for production access."
        ),
        actions=[
            "Wire human-in-the-loop into the credit-decision flow within 30 days.",
            "Adopt workload-identity federation for production access.",
            "Run a DPIA covering credit decisions and payment data within 60 days.",
            "Engage an EU AI Act conformity-assessment partner.",
        ],
    )
    dst = tmp_path / "report-summary.docx"

    proc = _run_builder(src, dst)
    assert proc.returncode == 0, proc.stderr

    assert zipfile.is_zipfile(dst)
    members = read_members(dst)
    assert "word/document.xml" in members
    assert any(name.startswith("word/footer") for name in members)

    document_xml = members["word/document.xml"]
    assert "Fintech app handling EU customer payment data" in document_xml
    for fw in ("GDPR", "PCI DSS", "EU AI Act", "SOC 2"):
        assert fw in document_xml, f"missing display name {fw}"
    assert "Key Findings" in document_xml
    assert "Priority Actions" in document_xml

    footer_xml = find_footer_xml(members)
    assert "Confidential — for internal use" in footer_xml
    assert "PAGE" in footer_xml


@pytest.mark.integration
def test_e2e_findings_capped_at_five_actions_at_three(tmp_path: Path) -> None:
    """8 findings + 7 actions → exactly 5 / 3 numbered items in the docx."""
    findings = " ".join(f"Findset sentence {i}." for i in range(1, 9))
    actions = [f"Actset {i}." for i in range(1, 8)]
    src = _write_report(
        tmp_path,
        frameworks=["GDPR", "SOC2"],
        findings_para=findings,
        actions=actions,
    )
    dst = tmp_path / "out.docx"

    proc = _run_builder(src, dst)
    assert proc.returncode == 0, proc.stderr

    members = read_members(dst)
    document_xml = members["word/document.xml"]

    finding_lines = re.findall(r"\b\d+\.\s+Findset sentence", document_xml)
    action_lines = re.findall(r"\b\d+\.\s+Actset \d+\.", document_xml)
    assert len(finding_lines) == 5, finding_lines
    assert len(action_lines) == 3, action_lines


@pytest.mark.integration
def test_e2e_subprocess_interface_matches_step_b_documentation(
    tmp_path: Path,
) -> None:
    """Builder invoked via Step B's exact flag names returns exit 0."""
    src = _write_report(
        tmp_path,
        frameworks=["GDPR"],
        findings_para="Single short sentence.",
        actions=["One action."],
    )
    dst = tmp_path / "out.docx"

    proc = subprocess.run(
        [
            sys.executable,
            str(BUILDER),
            "--in",
            str(src),
            "--out",
            str(dst),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert zipfile.is_zipfile(dst)
