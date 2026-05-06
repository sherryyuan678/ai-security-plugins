"""Tests for resolver semantic fixes: auto, display names, pub date, pre_effective (A2-A5)."""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PLUGIN_ROOT / "scripts" / "select_framework_versions.py"
INDEX = PLUGIN_ROOT / "data" / "framework_index.json"


def _run(args: list[str]) -> tuple[str, str, int]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--index", str(INDEX)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return proc.stdout, proc.stderr, proc.returncode


def test_auto_keyword_resolves_to_today_in_json() -> None:
    """S2: --as-of auto must resolve to today's UTC date in the JSON output."""
    out, err, rc = _run(["--as-of", "auto", "--format", "json"])
    assert rc == 0, err
    data = json.loads(out)
    assert data["as_of_date"] != "auto"
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    assert data["as_of_date"] == today


def test_markdown_uses_display_names() -> None:
    """S3: markdown should show 'SOC 2', 'ISO 27001', 'CCPA/CPRA', etc."""
    out, _, rc = _run(["--as-of", "2026-02-17", "--format", "markdown"])
    assert rc == 0
    assert "| SOC 2 |" in out
    assert "| ISO 27001 |" in out
    assert "| CCPA/CPRA |" in out
    assert "| EU AI Act |" in out
    assert "| PCI DSS |" in out
    assert "| NIST CSF |" in out
    # negative: raw underscored keys must not appear in markdown
    assert "| SOC2 |" not in out
    assert "| ISO_27001 |" not in out
    assert "| EU_AI_ACT |" not in out


def test_json_keeps_raw_keys() -> None:
    """S3-json: JSON output keys must remain raw (consumers depend on them)."""
    out, _, rc = _run(["--as-of", "2026-02-17", "--format", "json"])
    assert rc == 0
    data = json.loads(out)
    assert "SOC2" in data["frameworks"]
    assert "ISO_27001" in data["frameworks"]
    assert "EU_AI_ACT" in data["frameworks"]


def test_markdown_has_publication_date_column() -> None:
    """S4: markdown header must include 'Publication Date'."""
    out, _, rc = _run(["--as-of", "2026-02-17", "--format", "markdown"])
    assert rc == 0
    header = out.splitlines()[2]
    assert "Publication Date" in header


def test_pre_effective_status_for_historical_as_of() -> None:
    """S5: as-of before any effective date should yield pre_effective status."""
    out, _, rc = _run(
        ["--as-of", "2010-01-01", "--format", "json", "--framework", "GDPR"]
    )
    assert rc == 0
    data = json.loads(out)
    assert data["frameworks"]["GDPR"]["status"] == "pre_effective"


def test_pre_effective_renders_in_markdown_not_unresolved() -> None:
    """S5: pre_effective rows render full columns with a marker, not as UNRESOLVED."""
    out, _, rc = _run(
        ["--as-of", "2010-01-01", "--format", "markdown", "--framework", "GDPR"]
    )
    assert rc == 0
    body = "\n".join(out.splitlines()[3:])
    assert "UNRESOLVED" not in body
    assert "pre-effective" in body


def test_invalid_date_string_still_rejected() -> None:
    """parse_date keeps strict YYYY-MM-DD when value isn't 'auto'."""
    _, err, rc = _run(["--as-of", "not-a-date", "--format", "json"])
    assert rc != 0
    assert "does not match" in err or "ValueError" in err or "time data" in err


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
