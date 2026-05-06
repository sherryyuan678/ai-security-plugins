"""Tests for ``_canonical_set`` resolver-format key normalization.

The resolver in ``select_framework_versions.py`` emits JSON keys like
``ISO_27001``, ``PCI_DSS``, ``CCPA_CPRA``, ``NIST_CSF``, and ``EU_AI_ACT``.
When ``state.json`` is populated from that JSON, the validator must not
flag legitimate in-scope mentions as out-of-scope.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from validate_report import (  # type: ignore[import-not-found]  # noqa: E402
    _canonical_set,
    validate_compliance_file,
)


def test_canonical_set_normalizes_iso_27001_underscore() -> None:
    result = _canonical_set(["ISO_27001"])
    assert "iso 27001" in result


def test_canonical_set_normalizes_pci_dss_underscore() -> None:
    result = _canonical_set(["PCI_DSS"])
    assert "pci dss" in result


def test_canonical_set_normalizes_ccpa_cpra_underscore() -> None:
    """CCPA_CPRA → ccpa/cpra (canonical alias key uses slash, not space)."""
    result = _canonical_set(["CCPA_CPRA"])
    assert "ccpa/cpra" in result


def test_canonical_set_normalizes_nist_csf_underscore() -> None:
    result = _canonical_set(["NIST_CSF"])
    assert "nist csf" in result


def test_canonical_set_eu_ai_act_underscore() -> None:
    result = _canonical_set(["EU_AI_ACT"])
    assert "eu ai act" in result


def test_canonical_set_soc2_alias_still_works() -> None:
    result = _canonical_set(["SOC2"])
    assert "soc 2" in result


def test_canonical_set_display_form_still_works() -> None:
    result = _canonical_set(["SOC 2", "ISO 27001", "CCPA/CPRA"])
    assert {"soc 2", "iso 27001", "ccpa/cpra"} == result


def test_canonical_set_mixed_resolver_and_display() -> None:
    result = _canonical_set(["ISO_27001", "SOC 2", "CCPA_CPRA"])
    assert "iso 27001" in result
    assert "soc 2" in result
    assert "ccpa/cpra" in result


def test_canonical_set_unknown_underscore_kept_as_space() -> None:
    """Unknown frameworks must still survive normalization to be treated as in-scope."""
    result = _canonical_set(["FOO_BAR"])
    assert "foo bar" in result


def test_canonical_set_no_underscore_known_frameworks() -> None:
    """Frameworks without underscores or aliases (GDPR, HIPAA, DORA) must
    map onto the lowercased ALL_KNOWN_FRAMEWORKS form."""
    result = _canonical_set(["GDPR", "HIPAA", "DORA"])
    assert {"gdpr", "hipaa", "dora"} == result


def test_canonical_set_fedramp_and_cmmc() -> None:
    """FedRAMP and CMMC have alias entries; verify both casings normalize."""
    result = _canonical_set(["FedRAMP", "CMMC"])
    assert "fedramp" in result
    assert "cmmc" in result


def test_canonical_set_drops_boundary_underscore_junk() -> None:
    """Leading/trailing/all-underscore inputs must not pollute the set
    with whitespace-only entries."""
    result = _canonical_set(["_FOO", "BAR_", "___"])
    assert "foo" in result
    assert "bar" in result
    # All-underscore collapses to empty after strip and is dropped.
    assert "" not in result
    assert "   " not in result


def test_validate_does_not_flag_iso_27001_under_resolver_keys() -> None:
    """End-to-end: state.json with resolver keys must not flag legitimate
    ISO 27001 mentions in the body."""
    state = {"selected_frameworks": ["SOC2", "ISO_27001"]}
    content = (
        "# Applicability\n\n"
        "## Regulatory Applicability Assessment\n\n"
        "The organization is in scope for SOC 2 and ISO 27001.\n"
        "ISO 27001 Annex A controls apply.\n"
    )
    result = validate_compliance_file(content, "01-applicability.md", state)
    flagged = " | ".join(result["scope_violations"]).lower()
    assert "iso 27001" not in flagged
    assert "soc 2" not in flagged


def test_validate_does_not_flag_ccpa_under_resolver_keys() -> None:
    state = {"selected_frameworks": ["CCPA_CPRA"]}
    content = (
        "# Applicability\n\n"
        "## Regulatory Applicability Assessment\n\n"
        "Subject to CCPA/CPRA. CCPA notices required at collection.\n"
    )
    result = validate_compliance_file(content, "01-applicability.md", state)
    flagged = " | ".join(result["scope_violations"]).lower()
    assert "ccpa" not in flagged


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
