"""Tests for the PostToolUse hook ``validate_compliance_output.py``.

Specifically: spot-check files in ``.compliance-reports/`` must NOT load
``.compliance-check/state.json``. A stale state from a prior
compliance-check run would otherwise hijack the spot-check's frontmatter
scope and flag legitimate in-scope mentions as violations.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
HOOK_PATH = PLUGIN_ROOT / "hooks" / "validate_compliance_output.py"


def _run_hook(event: dict, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
        cwd=str(cwd),
        check=False,
    )


def test_spot_check_ignores_stale_state_json(tmp_path: Path) -> None:
    """Spot-check frontmatter must win over a stale .compliance-check/state.json."""
    (tmp_path / ".compliance-check").mkdir()
    (tmp_path / ".compliance-check" / "state.json").write_text(
        json.dumps({"selected_frameworks": ["SOC 2", "ISO 27001"]}),
        encoding="utf-8",
    )
    reports_dir = tmp_path / ".compliance-reports"
    reports_dir.mkdir()
    spot_check_path = reports_dir / "spot-check-2026-02-17-120000.md"

    content = (
        "---\n"
        "type: compliance-spot-check\n"
        "applicable_frameworks:\n"
        "  - CCPA/CPRA\n"
        "---\n\n"
        "## TL;DR\nReview the CCPA/CPRA posture.\n"
        "## Regulatory Applicability Assessment\nCCPA/CPRA applies.\n"
        "## Compliance Gap Summary\nGaps under CCPA/CPRA.\n"
        "## Cross-Framework Control Map\nMap.\n"
        "## Recommended Next Steps\nSteps.\n"
    )
    event = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(spot_check_path), "content": content},
        "cwd": str(tmp_path),
    }

    proc = _run_hook(event, tmp_path)
    assert proc.returncode == 0, proc.stderr

    if not proc.stdout.strip():
        return
    msg = json.loads(proc.stdout)["systemMessage"]
    assert "CCPA" not in msg.upper(), (
        "CCPA flagged despite being in spot-check applicable_frameworks: %s" % msg
    )


def test_compliance_check_still_uses_state_json(tmp_path: Path) -> None:
    """compliance-check files must still load state.json (regression guard)."""
    cc_dir = tmp_path / ".compliance-check"
    cc_dir.mkdir()
    (cc_dir / "state.json").write_text(
        json.dumps({"selected_frameworks": ["SOC 2"]}),
        encoding="utf-8",
    )
    cc_file = cc_dir / "01-applicability.md"
    content = (
        "# Applicability\n\n"
        "## Regulatory Applicability Assessment\n\n"
        "We must consider HIPAA implications carefully.\n"
    )
    event = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(cc_file), "content": content},
        "cwd": str(tmp_path),
    }

    proc = _run_hook(event, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip(), "expected HIPAA scope violation, got no output"
    msg = json.loads(proc.stdout)["systemMessage"]
    assert "HIPAA" in msg.upper()


def test_path_with_both_substrings_treated_as_report(tmp_path: Path) -> None:
    """When path contains both ``.compliance-check/`` and ``.compliance-reports/``,
    prefer report semantics so a stale state.json doesn't sneak in via substring
    overlap."""
    (tmp_path / ".compliance-check").mkdir()
    (tmp_path / ".compliance-check" / "state.json").write_text(
        json.dumps({"selected_frameworks": ["SOC 2"]}),
        encoding="utf-8",
    )
    nested = tmp_path / ".compliance-reports" / ".compliance-check"
    nested.mkdir(parents=True)
    spot_check_path = nested / "spot-check-2026-02-17-120000.md"
    content = (
        "---\n"
        "type: compliance-spot-check\n"
        "applicable_frameworks:\n"
        "  - CCPA/CPRA\n"
        "---\n\n"
        "## TL;DR\nCCPA/CPRA review.\n"
        "## Regulatory Applicability Assessment\nCCPA/CPRA applies.\n"
        "## Compliance Gap Summary\nGaps.\n"
        "## Cross-Framework Control Map\nMap.\n"
        "## Recommended Next Steps\nSteps.\n"
    )
    event = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(spot_check_path), "content": content},
        "cwd": str(tmp_path),
    }
    proc = _run_hook(event, tmp_path)
    assert proc.returncode == 0, proc.stderr
    if not proc.stdout.strip():
        return
    msg = json.loads(proc.stdout)["systemMessage"]
    assert "CCPA" not in msg.upper(), (
        "report-path with .compliance-check substring still loaded stale state: %s"
        % msg
    )


def test_edit_event_spot_check_ignores_stale_state(tmp_path: Path) -> None:
    """Edit/MultiEdit events read the file from disk; the same gate must
    apply so a spot-check Edit doesn't load stale state."""
    (tmp_path / ".compliance-check").mkdir()
    (tmp_path / ".compliance-check" / "state.json").write_text(
        json.dumps({"selected_frameworks": ["SOC 2", "ISO 27001"]}),
        encoding="utf-8",
    )
    reports_dir = tmp_path / ".compliance-reports"
    reports_dir.mkdir()
    spot_check_path = reports_dir / "spot-check-2026-02-17-120000.md"
    spot_check_path.write_text(
        "---\n"
        "type: compliance-spot-check\n"
        "applicable_frameworks:\n"
        "  - CCPA/CPRA\n"
        "---\n\n"
        "## TL;DR\nCCPA/CPRA review.\n"
        "## Regulatory Applicability Assessment\nCCPA/CPRA applies.\n"
        "## Compliance Gap Summary\nGaps.\n"
        "## Cross-Framework Control Map\nMap.\n"
        "## Recommended Next Steps\nSteps.\n",
        encoding="utf-8",
    )
    event = {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(spot_check_path)},
        "cwd": str(tmp_path),
    }
    proc = _run_hook(event, tmp_path)
    assert proc.returncode == 0, proc.stderr
    if not proc.stdout.strip():
        return
    msg = json.loads(proc.stdout)["systemMessage"]
    assert "CCPA" not in msg.upper(), (
        "Edit event for spot-check still loaded stale state: %s" % msg
    )


def test_spot_check_with_no_state_json_uses_frontmatter(tmp_path: Path) -> None:
    """When no state.json exists, frontmatter still drives scope (regression guard)."""
    reports_dir = tmp_path / ".compliance-reports"
    reports_dir.mkdir()
    spot_check_path = reports_dir / "spot-check-2026-02-17-120000.md"
    content = (
        "---\n"
        "type: compliance-spot-check\n"
        "applicable_frameworks:\n"
        "  - SOC 2 Type II\n"
        "---\n\n"
        "## TL;DR\nSOC 2 review.\n"
        "## Regulatory Applicability Assessment\nSOC 2.\n"
        "## Compliance Gap Summary\nSOC 2 gaps.\n"
        "## Cross-Framework Control Map\nMap.\n"
        "## Recommended Next Steps\n"
        "We will also consider HIPAA implications.\n"
    )
    event = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(spot_check_path), "content": content},
        "cwd": str(tmp_path),
    }
    proc = _run_hook(event, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip()
    msg = json.loads(proc.stdout)["systemMessage"]
    assert "HIPAA" in msg.upper()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
