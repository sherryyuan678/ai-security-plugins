"""End-to-end contract validation: resolver → synthesized markdown → validator.

Operates entirely on the LOCAL plugin tree. Does not touch the cached install
at ~/.claude/plugins/cache/.... Verifies that the fixes from B1, A1, A3, A5,
B3, A6, A7 hold together as a stack, not just in unit isolation.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
RESOLVER = SCRIPTS_DIR / "select_framework_versions.py"

sys.path.insert(0, str(SCRIPTS_DIR))

from validate_report import validate_compliance_file  # type: ignore[import-not-found]  # noqa: E402


@pytest.mark.integration
def test_resolver_runs_from_temp_cwd_and_produces_expected_columns(
    tmp_path: Path,
) -> None:
    """B1 + A1 + A3 + A5: resolver must run with no --index from any cwd
    and emit a markdown table whose header includes Publication Date,
    rows use display names, and pre-effective rows render with a marker
    (we don't trigger pre_effective here — the as-of date is current)."""
    proc = subprocess.run(
        [
            sys.executable,
            str(RESOLVER),
            "--as-of",
            "2026-02-17",
            "--format",
            "markdown",
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.splitlines()
    header = lines[2]
    assert "Publication Date" in header
    body = "\n".join(lines[3:])
    assert "| SOC 2 |" in body
    assert "| ISO 27001 |" in body
    assert "| CCPA/CPRA |" in body
    assert "| SOC2 |" not in body


@pytest.mark.integration
def test_synthesized_spot_check_with_inscope_only_validates_clean() -> None:
    """B3 happy path: applicable_frameworks frontmatter + body that mentions
    only those frameworks should produce no scope_violations."""
    content = (
        "---\n"
        "type: compliance-spot-check\n"
        "date: 2026-02-17\n"
        "applicable_frameworks:\n"
        "  - SOC 2 Type II\n"
        "  - ISO 27001\n"
        "  - GDPR\n"
        "  - DORA\n"
        "---\n\n"
        "## TL;DR\nGreen.\n"
        "## Regulatory Applicability Assessment\n"
        "SOC 2, ISO 27001, GDPR, DORA all apply.\n"
        "## Compliance Gap Summary\nNone.\n"
        "## Cross-Framework Control Map\nMapped.\n"
        "## Recommended Next Steps\nProceed.\n"
    )
    result = validate_compliance_file(
        content, "spot-check-2026-02-17-120000.md", state=None
    )
    assert result["scope_violations"] == []


@pytest.mark.integration
def test_synthesized_spot_check_flags_out_of_scope_hipaa() -> None:
    """B3 sad path: HIPAA in body but not in applicable_frameworks should
    surface a scope_violation (and strict_mode means an exclusion phrase
    earlier doesn't suppress an unrelated mention later)."""
    content = (
        "---\n"
        "type: compliance-spot-check\n"
        "date: 2026-02-17\n"
        "applicable_frameworks:\n"
        "  - SOC 2 Type II\n"
        "  - ISO 27001\n"
        "  - GDPR\n"
        "  - DORA\n"
        "---\n\n"
        "## TL;DR\nIn scope analysis.\n"
        "## Regulatory Applicability Assessment\n"
        "GDPR does not apply for the US-only sub-processor.\n"
        "\n"
        "## Compliance Gap Summary\nNone.\n"
        "\n"
        "## Cross-Framework Control Map\n"
        "Adopt HIPAA-style retention controls anyway.\n"
        "\n"
        "## Recommended Next Steps\nProceed.\n"
    )
    result = validate_compliance_file(
        content, "spot-check-2026-02-17-120000.md", state=None
    )
    flagged = " | ".join(result["scope_violations"]).lower()
    assert "hipaa" in flagged, result["scope_violations"]


@pytest.mark.integration
def test_synthesized_spot_check_alias_match_flags_bare_ccpa() -> None:
    """A6 + A7: a bare 'CCPA' mention is flagged when CCPA/CPRA is not
    in applicable_frameworks and the file is a spot-check (strict_mode)."""
    content = (
        "---\n"
        "type: compliance-spot-check\n"
        "date: 2026-02-17\n"
        "applicable_frameworks:\n"
        "  - SOC 2 Type II\n"
        "  - ISO 27001\n"
        "---\n\n"
        "## TL;DR\nReview.\n"
        "## Regulatory Applicability Assessment\nSOC 2 and ISO 27001 apply.\n"
        "## Compliance Gap Summary\n"
        "We acknowledge that CCPA disclosures are required.\n"
        "## Cross-Framework Control Map\nMapped.\n"
        "## Recommended Next Steps\nProceed.\n"
    )
    result = validate_compliance_file(
        content, "spot-check-2026-02-17-120000.md", state=None
    )
    flagged = " | ".join(result["scope_violations"]).lower()
    assert "ccpa" in flagged, result["scope_violations"]


@pytest.mark.integration
def test_section_checklist_fires_for_spot_check() -> None:
    """The validator must surface missing required sections for spot-check
    files (B3 — section checklist)."""
    content = (
        "---\n"
        "type: compliance-spot-check\n"
        "date: 2026-02-17\n"
        "applicable_frameworks:\n"
        "  - SOC 2 Type II\n"
        "---\n\n"
        "# Title\n\n"
        "## TL;DR\nx\n"
    )
    result = validate_compliance_file(
        content, "spot-check-2026-02-17-120000.md", state=None
    )
    warnings = " | ".join(result["warnings"])
    assert "Compliance Gap Summary" in warnings
    assert "Cross-Framework Control Map" in warnings
    assert "Recommended Next Steps" in warnings


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
