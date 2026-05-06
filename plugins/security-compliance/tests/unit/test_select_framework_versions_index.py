"""Tests for resolver index-path discovery (B1, A1)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PLUGIN_ROOT / "scripts" / "select_framework_versions.py"
DEFAULT_INDEX = PLUGIN_ROOT / "data" / "framework_index.json"


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_explicit_index_arg_works(tmp_path: Path) -> None:
    """Passing --index explicitly resolves the index regardless of cwd."""
    result = _run(
        ["--as-of", "2026-02-17", "--index", str(DEFAULT_INDEX), "--format", "json"],
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "frameworks" in result.stdout


def test_no_index_arg_uses_script_relative_path(tmp_path: Path) -> None:
    """Without --index and from a non-plugin cwd, the script-relative fallback fires."""
    result = _run(["--as-of", "2026-02-17", "--format", "json"], cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "frameworks" in result.stdout


def test_no_index_arg_from_repo_root_works() -> None:
    """From the repo root (typical Claude Code cwd), no --index should still work."""
    repo_root = PLUGIN_ROOT.parents[1]
    result = _run(["--as-of", "2026-02-17", "--format", "json"], cwd=repo_root)
    assert result.returncode == 0, result.stderr


def test_explicit_index_overrides_script_relative(tmp_path: Path) -> None:
    """An explicit --index takes precedence over the script-relative fallback."""
    bogus = tmp_path / "framework_index.json"
    bogus.write_text('{"frameworks": {}}', encoding="utf-8")
    result = _run(
        ["--as-of", "2026-02-17", "--index", str(bogus), "--format", "json"],
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert '"frameworks": {}' in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
