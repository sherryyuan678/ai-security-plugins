"""Tests for matcher API: strict mode, alias-aware, paragraph-bounded (A6, A7, A8)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from matching import (  # type: ignore[import-not-found]  # noqa: E402
    contains_forbidden_with_context,
    is_exclusion_context,
)


def test_strict_mode_disables_exclusion_bypass() -> None:
    """A7: in strict mode, an out-of-scope mention inside an exclusion
    paragraph is still flagged."""
    text = "HIPAA is not applicable to this scenario.\n"
    hits, ignored = contains_forbidden_with_context(text, ["HIPAA"], strict_mode=True)
    assert "HIPAA" in hits
    assert "HIPAA" not in ignored


def test_default_mode_keeps_exclusion_bypass() -> None:
    """Default mode preserves the existing behavior — exclusion contexts
    suppress the hit. run_eval.py and other callers depend on this."""
    text = "HIPAA is not applicable to this scenario.\n"
    hits, ignored = contains_forbidden_with_context(text, ["HIPAA"])
    assert "HIPAA" not in hits
    assert "HIPAA" in ignored


def test_alias_match_catches_bare_ccpa_when_canonical_excluded() -> None:
    """A6: a bare 'CCPA' mention is flagged when the canonical
    'CCPA/CPRA' is in the forbidden list."""
    text = "We acknowledge that CCPA disclosures are required.\n"
    hits, _ = contains_forbidden_with_context(text, ["CCPA/CPRA"], strict_mode=True)
    assert "CCPA/CPRA" in hits


def test_alias_match_catches_iso_27001_2022() -> None:
    """ISO/IEC 27001 (and ISO 27001:2022) is recognized as ISO 27001."""
    text = "We rely on ISO/IEC 27001 controls.\n"
    hits, _ = contains_forbidden_with_context(text, ["ISO 27001"], strict_mode=True)
    assert "ISO 27001" in hits


def test_paragraph_bounded_exclusion_does_not_overreach() -> None:
    """A8: an exclusion sentence in one paragraph should not suppress a
    later out-of-scope mention in a separate paragraph."""
    text = (
        "GDPR does not apply because this is a US-only system.\n"
        "\n"
        "## Cross-Border Considerations\n"
        "\n"
        "We process payments under HIPAA-style controls.\n"
    )
    hits, _ = contains_forbidden_with_context(text, ["HIPAA"])
    assert "HIPAA" in hits


def test_exclusion_context_within_same_paragraph_still_suppresses() -> None:
    """When the exclusion phrase and the framework name are in the same
    paragraph, the bypass should still apply (default mode)."""
    text = (
        "## Scope Boundary\n"
        "\n"
        "FedRAMP does not apply to this commercial deployment;\n"
        "FedRAMP authorization would only be needed for federal customers.\n"
    )
    hits, ignored = contains_forbidden_with_context(text, ["FedRAMP"])
    assert "FedRAMP" not in hits
    assert "FedRAMP" in ignored


def test_is_exclusion_context_strict_mode_returns_false() -> None:
    lines = ["", "", "HIPAA is not applicable.", "extra"]
    assert is_exclusion_context(lines, 2, strict_mode=False)
    assert not is_exclusion_context(lines, 2, strict_mode=True)


def test_run_eval_default_signature_unchanged() -> None:
    """S8-eval: existing callers (run_eval.py, validate_report.py default
    branch) must still work without supplying strict_mode."""
    text = "GDPR is mentioned here.\n"
    hits, _ = contains_forbidden_with_context(text, ["GDPR"])
    assert "GDPR" in hits


def test_unknown_framework_name_falls_back_to_literal() -> None:
    """When the canonical name is not in FRAMEWORK_ALIASES (e.g. plain
    'GDPR'), substring matching should still work as before."""
    text = "GDPR Article 32 applies.\n"
    hits, _ = contains_forbidden_with_context(text, ["GDPR"], strict_mode=True)
    assert "GDPR" in hits


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
