"""Tests for check_dependencies python-docx probe and lazy install."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = PLUGIN_ROOT / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import check_dependencies  # type: ignore[import-not-found]  # noqa: E402


def _completed(returncode: int, stderr: str = "") -> subprocess.CompletedProcess:
    """Build a CompletedProcess fixture for the runner mock."""
    return subprocess.CompletedProcess(
        args=["python", "-c", "..."], returncode=returncode, stdout="", stderr=stderr
    )


def _run_main_capture_stdout(
    runner_for_probe: Any, runner_for_install: Any = None
) -> str:
    """Invoke ``main()`` with mocked subprocess runners; return captured stdout."""
    buf = io.StringIO()

    def patched_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        cmd = args[0]
        cmd_str = " ".join(str(c) for c in cmd)
        if "find_spec('docx')" in cmd_str or "import docx" in cmd_str:
            return runner_for_probe(*args, **kwargs)
        if "install" in cmd and any(
            isinstance(c, str) and c.startswith("python-docx") for c in cmd
        ):
            assert runner_for_install is not None, "install runner not provided"
            return runner_for_install(*args, **kwargs)
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    with patch.object(check_dependencies.subprocess, "run", side_effect=patched_run):
        with patch.object(check_dependencies.sys, "stdout", buf):
            check_dependencies.main()
    return buf.getvalue()


def test_probe_silent_when_docx_present_no_cowork(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """python-docx importable, not Cowork → empty stdout, no install attempt."""
    monkeypatch.delenv("CLAUDE_COWORK", raising=False)
    output = _run_main_capture_stdout(lambda *a, **k: _completed(0))
    assert output == ""


def test_probe_silent_when_docx_present_inside_cowork(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """python-docx importable inside Cowork → still empty (no Cowork early-return)."""
    monkeypatch.setenv("CLAUDE_COWORK", "1")
    output = _run_main_capture_stdout(lambda *a, **k: _completed(0))
    assert output == ""


def test_install_attempted_when_docx_missing_outside_cowork(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outside Cowork: missing → pip install --user runs, success message emitted."""
    monkeypatch.delenv("CLAUDE_COWORK", raising=False)
    output = _run_main_capture_stdout(
        runner_for_probe=lambda *a, **k: _completed(1, stderr="ModuleNotFoundError"),
        runner_for_install=lambda *a, **k: _completed(0),
    )
    payload = json.loads(output.strip())
    assert "python-docx installed" in payload["systemMessage"]


def test_install_attempted_when_docx_missing_inside_cowork(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cowork + missing → install attempted (regression test for prior early-return bug)."""
    monkeypatch.setenv("CLAUDE_COWORK", "1")
    output = _run_main_capture_stdout(
        runner_for_probe=lambda *a, **k: _completed(1, stderr="ModuleNotFoundError"),
        runner_for_install=lambda *a, **k: _completed(0),
    )
    payload = json.loads(output.strip())
    assert "python-docx installed" in payload["systemMessage"]


def test_install_failure_emits_first_stderr_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pip nonzero exit → systemMessage includes the first stderr line."""
    monkeypatch.delenv("CLAUDE_COWORK", raising=False)
    output = _run_main_capture_stdout(
        runner_for_probe=lambda *a, **k: _completed(1),
        runner_for_install=lambda *a, **k: _completed(
            1, stderr="ERROR: package resolver could not satisfy constraints\n"
        ),
    )
    payload = json.loads(output.strip())
    assert "install failed" in payload["systemMessage"]
    assert "package resolver" in payload["systemMessage"]


def test_install_timeout_emits_timeout_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pip TimeoutExpired → systemMessage names the timeout."""
    monkeypatch.delenv("CLAUDE_COWORK", raising=False)

    def install_timeout(*a: Any, **k: Any) -> subprocess.CompletedProcess:
        raise subprocess.TimeoutExpired(cmd="pip", timeout=60)

    output = _run_main_capture_stdout(
        runner_for_probe=lambda *a, **k: _completed(1),
        runner_for_install=install_timeout,
    )
    payload = json.loads(output.strip())
    assert "timed out" in payload["systemMessage"]


def test_probe_runs_safely_without_disabling_user_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe must run with cwd=/ + sanitized env, but NOT with python -I.

    -I disables user site-packages (`site.ENABLE_USER_SITE = False`), which
    would prevent the probe from seeing the result of `pip install --user`.
    Hardening is provided by cwd=/ + PYTHONPATH/PYTHONHOME stripping +
    `find_spec` (no execution), so -I is unnecessary and harmful.
    """
    captured: dict = {}

    def capture(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _completed(0)

    monkeypatch.delenv("CLAUDE_COWORK", raising=False)
    monkeypatch.setenv("PYTHONPATH", "/tmp/hostile")
    monkeypatch.setenv("PYTHONHOME", "/tmp/hostile-home")
    check_dependencies.python_docx_available(runner=capture)

    cmd = captured["args"][0]
    assert "-I" not in cmd, (
        "probe must NOT use -I (it disables user-site and breaks idempotence)"
    )
    assert "find_spec('docx')" in " ".join(cmd), (
        "probe must use importlib.util.find_spec, not import docx"
    )
    assert captured["kwargs"]["cwd"] == "/", "probe must run with cwd=/"
    env = captured["kwargs"]["env"]
    assert "PYTHONPATH" not in env, "probe env must strip PYTHONPATH"
    assert "PYTHONHOME" not in env, "probe env must strip PYTHONHOME"


def test_install_uses_pinned_binary_only_flags_no_python_minus_I(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Install must use pip --isolated, --user, --only-binary :all:, version pin.

    Python is NOT invoked with -I because -I + --user is contradictory: -I
    disables the user site that --user installs into, so a successful install
    would not be visible to the next probe. Pip's own --isolated provides
    config-file isolation; cwd=/ + sanitized env handle process isolation.
    """
    captured: dict = {}

    def capture(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _completed(0)

    monkeypatch.delenv("CLAUDE_COWORK", raising=False)
    monkeypatch.setenv("PYTHONPATH", "/tmp/hostile")
    check_dependencies.install_python_docx(runner=capture)

    cmd = captured["args"][0]
    assert "-I" not in cmd, "python -I must not be paired with pip --user"
    for flag in ("--isolated", "--no-input", "--disable-pip-version-check"):
        assert flag in cmd, f"install must include {flag}"
    assert "--only-binary=:all:" in cmd, "install must include --only-binary=:all:"
    assert "--user" in cmd, "install must target --user"
    assert any(c.startswith("python-docx>=") for c in cmd), (
        "install must pin python-docx version range"
    )
    assert captured["kwargs"]["cwd"] == "/", "install must run with cwd=/"
    env = captured["kwargs"]["env"]
    assert "PYTHONPATH" not in env
    assert "PYTHONHOME" not in env


def test_idempotence_after_user_install_in_real_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: install python-docx into a fake user-site → probe sees it.

    Simulates the post-install state by creating a stub ``docx`` package
    inside a user-site path and pointing PYTHONUSERBASE at it. The
    sanitized env still preserves PYTHONUSERBASE (only PYTHONPATH /
    PYTHONHOME are stripped), so the probe finds the stub. Without the
    -I removal, this test would fail because -I disables user-site.
    """
    user_base = tmp_path / "user-base"
    py_ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    user_site = user_base / "lib" / py_ver / "site-packages"
    docx_stub = user_site / "docx"
    docx_stub.mkdir(parents=True)
    (docx_stub / "__init__.py").write_text("__version__ = 'test'\n", encoding="utf-8")

    monkeypatch.setenv("PYTHONUSERBASE", str(user_base))
    monkeypatch.delenv("CLAUDE_COWORK", raising=False)
    assert check_dependencies.python_docx_available() is True


def test_main_silent_when_user_site_already_has_docx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression for /cx pr finding 1: post-install probe must be silent."""
    user_base = tmp_path / "user-base"
    py_ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    user_site = user_base / "lib" / py_ver / "site-packages"
    docx_stub = user_site / "docx"
    docx_stub.mkdir(parents=True)
    (docx_stub / "__init__.py").write_text("__version__ = 'test'\n", encoding="utf-8")

    monkeypatch.setenv("PYTHONUSERBASE", str(user_base))
    monkeypatch.delenv("CLAUDE_COWORK", raising=False)

    buf = io.StringIO()
    real_run = subprocess.run

    def passthrough(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        cmd = args[0]
        cmd_str = " ".join(str(c) for c in cmd)
        if "find_spec('docx')" in cmd_str:
            return real_run(*args, **kwargs)
        raise AssertionError(
            f"main() should not call install when probe is True: {cmd}"
        )

    with patch.object(check_dependencies.subprocess, "run", side_effect=passthrough):
        with patch.object(check_dependencies.sys, "stdout", buf):
            check_dependencies.main()

    assert buf.getvalue() == "", (
        f"hook must be silent when docx is already in user-site, got: {buf.getvalue()!r}"
    )


def test_main_never_raises_on_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even when subprocess.run raises an unexpected exception, main() exits cleanly."""
    monkeypatch.delenv("CLAUDE_COWORK", raising=False)
    buf = io.StringIO()

    def raising_run(*a: Any, **k: Any) -> Any:
        raise RuntimeError("unexpected failure")

    with patch.object(check_dependencies.subprocess, "run", side_effect=raising_run):
        with patch.object(check_dependencies.sys, "stdout", buf):
            check_dependencies.main()
    output = buf.getvalue()
    payload = json.loads(output.strip())
    assert "dependency check error" in payload["systemMessage"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
