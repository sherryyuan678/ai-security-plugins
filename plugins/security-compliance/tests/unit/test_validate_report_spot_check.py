"""Tests for spot-check validation in validate_report.py (B3)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from validate_report import (  # type: ignore[import-not-found]  # noqa: E402
    SPOT_CHECK_FILENAME_RE,
    SPOT_CHECK_REQUIRED_SECTIONS,
    check_required_sections,
    parse_frontmatter,
    validate_compliance_file,
)


SPOT_CHECK_FILENAME = "spot-check-2026-02-17-120000.md"


def test_filename_regex_matches_spot_check_with_seconds() -> None:
    assert SPOT_CHECK_FILENAME_RE.match("spot-check-2026-02-17-120000.md")
    assert SPOT_CHECK_FILENAME_RE.match("spot-check-2026-02-17.md")
    assert not SPOT_CHECK_FILENAME_RE.match("01-applicability.md")


def test_required_sections_picks_spot_check_checklist() -> None:
    body = "# Title\n\n## TL;DR\nx\n## Regulatory Applicability Assessment\nx\n"
    missing = check_required_sections(body, SPOT_CHECK_FILENAME)
    expected_missing = {
        "Compliance Gap Summary",
        "Cross-Framework Control Map",
        "Recommended Next Steps",
    }
    assert set(missing) == expected_missing


def test_required_sections_full_spot_check_body_passes() -> None:
    body = "\n".join(f"## {section}\n" for section in SPOT_CHECK_REQUIRED_SECTIONS)
    assert check_required_sections(body, SPOT_CHECK_FILENAME) == []


def test_required_sections_toc_only_does_not_satisfy() -> None:
    """ToC links must not satisfy the section-presence check; only an
    actual heading line counts."""
    body = (
        "# Compliance Spot-Check\n\n"
        "## Table of Contents\n\n"
        "- [TL;DR](#tldr)\n"
        "- [Regulatory Applicability Assessment](#regulatory-applicability-assessment)\n"
        "- [Compliance Gap Summary](#compliance-gap-summary)\n"
        "- [Cross-Framework Control Map](#cross-framework-control-map)\n"
        "- [Recommended Next Steps](#recommended-next-steps)\n\n"
        "Body without any actual section headings.\n"
    )
    missing = set(check_required_sections(body, SPOT_CHECK_FILENAME))
    assert missing == set(SPOT_CHECK_REQUIRED_SECTIONS)


def test_required_sections_inline_mention_does_not_satisfy() -> None:
    """Inline prose mention of a section name is not a heading."""
    body = (
        "# Title\n\n"
        "We will discuss the TL;DR in detail below, including the\n"
        "Regulatory Applicability Assessment and Compliance Gap Summary.\n"
    )
    missing = set(check_required_sections(body, SPOT_CHECK_FILENAME))
    assert missing == set(SPOT_CHECK_REQUIRED_SECTIONS)


def test_required_sections_h1_h3_all_count() -> None:
    """Heading levels 1-6 all satisfy the check."""
    body = (
        "# TL;DR\n\n"
        "## Regulatory Applicability Assessment\n\n"
        "### Compliance Gap Summary\n\n"
        "#### Cross-Framework Control Map\n\n"
        "##### Recommended Next Steps\n\n"
    )
    assert check_required_sections(body, SPOT_CHECK_FILENAME) == []


def test_required_sections_compliance_check_partial_match() -> None:
    """REQUIRED_SECTIONS entries are prefixes; a heading like
    ``## Cross-Framework Control Map`` satisfies entry
    ``Cross-Framework Control``."""
    body = "# Title\n\n## Cross-Framework Control Map\n\nMapped controls.\n"
    assert check_required_sections(body, "02-control-map.md") == []


def test_required_sections_hyphen_suffix_does_not_satisfy() -> None:
    """``## Compliance Gap-Notes`` must NOT satisfy ``Compliance Gap`` —
    the hyphen makes it a different identifier."""
    body = "# Title\n\n## Compliance Gap-Notes\n\nNotes.\n"
    assert check_required_sections(body, "03-gap-analysis.md") == ["Compliance Gap"]


def test_required_sections_underscore_suffix_does_not_satisfy() -> None:
    """``## TL;DR_Section`` must NOT satisfy ``TL;DR`` — underscore is a word char."""
    body = (
        "# Title\n\n## TL;DR_Section\n\n"
        "## Regulatory Applicability Assessment\n\n"
        "## Compliance Gap Summary\n\n"
        "## Cross-Framework Control Map\n\n"
        "## Recommended Next Steps\n"
    )
    missing = check_required_sections(body, SPOT_CHECK_FILENAME)
    assert "TL;DR" in missing


def test_required_sections_fenced_code_block_does_not_satisfy() -> None:
    """A heading inside a fenced code block must not count."""
    body = (
        "# Title\n\n"
        "Here is a markdown example:\n\n"
        "```md\n"
        "## TL;DR\n"
        "## Regulatory Applicability Assessment\n"
        "## Compliance Gap Summary\n"
        "## Cross-Framework Control Map\n"
        "## Recommended Next Steps\n"
        "```\n\n"
        "Real body has no headings.\n"
    )
    missing = set(check_required_sections(body, SPOT_CHECK_FILENAME))
    assert missing == set(SPOT_CHECK_REQUIRED_SECTIONS)


def test_required_sections_tilde_fence_also_stripped() -> None:
    """Tilde-fenced code blocks (~~~) are stripped just like backtick fences."""
    body = (
        "# Title\n\n"
        "~~~md\n"
        "## TL;DR\n"
        "~~~\n\n"
        "## Regulatory Applicability Assessment\n\n"
        "## Compliance Gap Summary\n\n"
        "## Cross-Framework Control Map\n\n"
        "## Recommended Next Steps\n"
    )
    missing = check_required_sections(body, SPOT_CHECK_FILENAME)
    assert missing == ["TL;DR"]


def test_required_sections_indented_heading_up_to_three_spaces() -> None:
    """CommonMark allows up to 3 leading spaces; 4+ is a code block."""
    body = (
        "# Title\n\n"
        "   ## TL;DR\n\n"
        "   ## Regulatory Applicability Assessment\n\n"
        "## Compliance Gap Summary\n\n"
        "## Cross-Framework Control Map\n\n"
        "## Recommended Next Steps\n"
    )
    assert check_required_sections(body, SPOT_CHECK_FILENAME) == []


def test_required_sections_h6_counts() -> None:
    """h6 (six hashes) is the maximum heading level and must satisfy."""
    body = (
        "###### TL;DR\n"
        "###### Regulatory Applicability Assessment\n"
        "###### Compliance Gap Summary\n"
        "###### Cross-Framework Control Map\n"
        "###### Recommended Next Steps\n"
    )
    assert check_required_sections(body, SPOT_CHECK_FILENAME) == []


def test_required_sections_frontmatter_comment_does_not_false_positive() -> None:
    """A YAML comment starting with ``# TL;DR`` inside frontmatter must NOT
    satisfy the section check."""
    body = (
        "---\n"
        "type: compliance-spot-check\n"
        "# TL;DR is in the frontmatter as a comment\n"
        "---\n\n"
        "Body without sections.\n"
    )
    missing = set(check_required_sections(body, SPOT_CHECK_FILENAME))
    assert missing == set(SPOT_CHECK_REQUIRED_SECTIONS)


def test_parse_frontmatter_inline_scalars() -> None:
    content = (
        "---\n"
        "type: compliance-spot-check\n"
        "date: 2026-02-17\n"
        'scenario: "fintech app"\n'
        "industry: SaaS\n"
        "---\n\nbody\n"
    )
    parsed = parse_frontmatter(content)
    assert parsed["type"] == "compliance-spot-check"
    assert parsed["date"] == "2026-02-17"
    assert parsed["scenario"] == "fintech app"
    assert parsed["industry"] == "SaaS"


def test_parse_frontmatter_block_list() -> None:
    content = (
        "---\n"
        "applicable_frameworks:\n"
        "  - SOC 2 Type II\n"
        "  - ISO 27001\n"
        "  - GDPR\n"
        "  - DORA\n"
        "---\n"
    )
    parsed = parse_frontmatter(content)
    assert parsed["applicable_frameworks"] == [
        "SOC 2 Type II",
        "ISO 27001",
        "GDPR",
        "DORA",
    ]


def test_parse_frontmatter_returns_empty_when_missing() -> None:
    assert parse_frontmatter("# No frontmatter\n\nBody.\n") == {}


def test_validate_spot_check_flags_out_of_scope_framework() -> None:
    """A spot-check file mentioning HIPAA when not in applicable_frameworks
    should produce a scope_violation entry."""
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
        "# Compliance Spot-Check\n\n"
        "## TL;DR\nLooks fine.\n"
        "## Regulatory Applicability Assessment\nSOC 2, ISO 27001, GDPR apply.\n"
        "## Compliance Gap Summary\nGaps in DORA.\n"
        "## Cross-Framework Control Map\nMapped controls.\n"
        "## Recommended Next Steps\n"
        "Adopt HIPAA-style retention controls anyway.\n"
    )
    result = validate_compliance_file(content, SPOT_CHECK_FILENAME, state=None)
    flagged = " | ".join(result["scope_violations"]).lower()
    assert "hipaa" in flagged


def test_validate_spot_check_clean_when_only_applicable_mentioned() -> None:
    content = (
        "---\n"
        "type: compliance-spot-check\n"
        "date: 2026-02-17\n"
        "applicable_frameworks:\n"
        "  - SOC 2 Type II\n"
        "  - ISO 27001\n"
        "---\n\n"
        "## TL;DR\n## Regulatory Applicability Assessment\nSOC 2 and ISO 27001.\n"
        "## Compliance Gap Summary\n## Cross-Framework Control Map\n"
        "## Recommended Next Steps\n"
    )
    result = validate_compliance_file(content, SPOT_CHECK_FILENAME, state=None)
    assert result["scope_violations"] == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
