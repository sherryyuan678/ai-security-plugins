"""Tests for resolve_frameworks hook --as-of parsing (B2)."""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = PLUGIN_ROOT / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import resolve_frameworks  # type: ignore[import-not-found]  # noqa: E402


def _today_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def test_extract_as_of_with_explicit_date() -> None:
    """A well-formed --as-of date in the prompt is returned verbatim."""
    prompt = "/security-compliance:spot-check --as-of 2026-02-17 healthcare app"
    assert resolve_frameworks.extract_as_of(prompt) == "2026-02-17"


def test_extract_as_of_auto_resolves_to_today() -> None:
    """The literal 'auto' falls back to today's UTC date."""
    prompt = "/security-compliance:spot-check --as-of auto SaaS scenario"
    assert resolve_frameworks.extract_as_of(prompt) == _today_utc()


def test_extract_as_of_missing_falls_back_to_today() -> None:
    """When --as-of is absent, the hook uses today."""
    prompt = "/security-compliance:spot-check fintech compliance"
    assert resolve_frameworks.extract_as_of(prompt) == _today_utc()


def test_extract_as_of_invalid_falls_back_silently() -> None:
    """A garbage date string never crashes — fall back to today."""
    prompt = "/security-compliance:spot-check --as-of 99-99-99"
    assert resolve_frameworks.extract_as_of(prompt) == _today_utc()


def test_extract_as_of_only_matches_yyyy_mm_dd_or_auto() -> None:
    """Other date shapes are ignored (regex bounds the contract)."""
    prompt = "/security-compliance:spot-check --as-of February 17, 2026"
    assert resolve_frameworks.extract_as_of(prompt) == _today_utc()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
