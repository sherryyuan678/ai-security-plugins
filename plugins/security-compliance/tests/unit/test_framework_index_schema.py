"""Schema invariants for data/framework_index.json (A9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
INDEX = PLUGIN_ROOT / "data" / "framework_index.json"


@pytest.fixture(scope="module")
def index() -> dict:
    return json.loads(INDEX.read_text(encoding="utf-8"))


def test_index_loads(index: dict) -> None:
    """Sanity: framework_index.json is valid JSON with the expected top-level keys."""
    assert "iam_control_families" in index
    assert "frameworks" in index
    assert isinstance(index["frameworks"], dict)


def test_every_framework_covers_all_iam_families(index: dict) -> None:
    """Every framework's first version must have iam_control_family_refs that
    cover every key in the iam_control_families taxonomy. Underscore-prefixed
    keys (e.g. _note) are allowed as additional metadata."""
    families = set(index["iam_control_families"].keys())
    failures = []
    for name, versions in index["frameworks"].items():
        assert versions, f"{name} has no versions"
        first = versions[0]
        refs = first.get("iam_control_family_refs", {})
        ref_keys = {k for k in refs if not k.startswith("_")}
        if ref_keys != families:
            missing = sorted(families - ref_keys)
            extra = sorted(ref_keys - families)
            failures.append((name, missing, extra))
    assert not failures, f"Family coverage mismatch: {failures}"


def test_ccpa_uses_1798_81_5_for_filled_in_families(index: dict) -> None:
    """A9 hardening: the CCPA_CPRA refs added in this fix should anchor to
    §1798.81.5 (the documented 'reasonable security' umbrella)."""
    refs = index["frameworks"]["CCPA_CPRA"][0]["iam_control_family_refs"]
    for family in (
        "authentication",
        "identifier_management",
        "credential_lifecycle",
        "session_management",
        "joiner_mover_leaver",
        "access_review",
        "machine_identity",
    ):
        joined = " ".join(refs[family])
        assert "1798.81.5" in joined, (
            f"{family} should anchor to §1798.81.5, got: {joined}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
