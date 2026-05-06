#!/usr/bin/env python3
"""SessionStart hook: probe for python-docx, lazy-install if missing.

The plugin's DOCX summary builder (``scripts/build_docx_summary.py``) imports
``python-docx``. This hook checks whether the dependency is importable in the
running interpreter; if not, it attempts a one-shot ``pip install --user
python-docx`` and emits a single-line ``systemMessage``. Always exits 0 per
the SessionStart hook contract — failures are reported, not propagated as
non-zero exit codes.

Live surface: ``python_docx_available`` (probe) + ``install_python_docx``
(lazy install) + ``emit`` (systemMessage JSON to stdout) + ``main``
(probe → install → emit). The constants ``PROBE_TIMEOUT_SECONDS``,
``INSTALL_TIMEOUT_SECONDS``, ``PROBE_CODE``, and ``SAFE_CWD`` are tuning
knobs.

Hardening: every subprocess invocation runs with ``cwd=/`` and a sanitized
environment (``PYTHONPATH`` / ``PYTHONHOME`` cleared) so a hostile
``docx.py`` / ``pip.py`` shadow in the hook's working directory cannot
execute on session start. The probe uses ``importlib.util.find_spec``,
which locates the module without importing it. The install runs with
``--isolated --no-input --disable-pip-version-check --only-binary=:all:``
so a malicious sdist build script in a transitive dep cannot run.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PROBE_TIMEOUT_SECONDS = 3
INSTALL_TIMEOUT_SECONDS = 60

PROBE_CODE = (
    "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('docx') else 1)"
)


def safe_subprocess_env() -> dict[str, str]:
    """Return a sanitized env dict with PYTHONPATH/PYTHONHOME stripped."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    return env


SAFE_CWD = "/"


def python_docx_available(runner: Any = None) -> bool:
    """Return True when ``docx`` is importable in the current interpreter.

    Uses ``importlib.util.find_spec`` so the module is located without being
    executed. Runs from ``/`` with ``PYTHONPATH``/``PYTHONHOME`` stripped so a
    repo-local ``docx.py`` shadow cannot hijack the probe.

    Does NOT use ``python -I``: ``-I`` disables user site-packages
    (``site.ENABLE_USER_SITE`` becomes ``False``), but ``install_python_docx``
    targets ``--user``. Probing with ``-I`` after a successful install would
    not find the just-installed module, so the hook would re-install on
    every SessionStart. ``cwd=/`` plus the stripped env give cwd/env
    isolation without hiding user-site.

    ``runner`` is a hook for tests; defaults to ``subprocess.run``.
    """
    runner = runner or subprocess.run
    try:
        proc = runner(
            [sys.executable, "-c", PROBE_CODE],
            capture_output=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
            cwd=SAFE_CWD,
            env=safe_subprocess_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def install_python_docx(runner: Any = None) -> dict[str, Any]:
    """Attempt ``pip install --user python-docx``; return a result dict.

    Targets ``sys.executable`` so the install lands in the same interpreter
    the next probe will use. Pip runs with ``--isolated --no-input
    --disable-pip-version-check --only-binary=:all:`` so a malicious sdist
    build script in a transitive dependency cannot execute. The subprocess
    starts in ``cwd=/`` with ``PYTHONPATH``/``PYTHONHOME`` stripped so a
    repo-local ``pip.py`` shadow cannot hijack the install. Returns a dict
    with keys ``ok`` (bool) and ``message`` (str). Never raises.
    """
    runner = runner or subprocess.run
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "--isolated",
        "--no-input",
        "--disable-pip-version-check",
        "install",
        "--user",
        "--only-binary=:all:",
        "python-docx>=1.1,<2",
    ]
    try:
        proc = runner(
            cmd,
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT_SECONDS,
            check=False,
            cwd=SAFE_CWD,
            env=safe_subprocess_env(),
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "message": (
                "security-compliance: python-docx install timed out after "
                "%ds; DOCX generation will fail until installed manually"
                % INSTALL_TIMEOUT_SECONDS
            ),
        }
    except OSError as exc:
        return {
            "ok": False,
            "message": "security-compliance: python-docx install could not start: %s"
            % exc,
        }
    if proc.returncode == 0:
        return {
            "ok": True,
            "message": "security-compliance: python-docx installed via pip --user",
        }
    stderr_first_line = (proc.stderr or "").strip().splitlines()[:1]
    detail = (
        stderr_first_line[0] if stderr_first_line else ("exit %d" % proc.returncode)
    )
    return {
        "ok": False,
        "message": "security-compliance: python-docx install failed: %s" % detail,
    }


def emit(message: str) -> None:
    """Write a single-line ``systemMessage`` JSON to stdout."""
    sys.stdout.write(json.dumps({"systemMessage": message}) + "\n")


SOFFICE_MAC_CANONICAL = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
SOFFICE_LINUX_CANONICAL = "/usr/bin/soffice"
SOFFICE_BREW = "/opt/homebrew/bin/soffice"
SOFFICE_MIN_VERSION = (7, 5)


def _probe_soffice() -> dict[str, Any]:
    """Probe for soffice (LibreOffice). Soft-fail with install hints.

    The edit-docx --accept-changes path requires soffice >= 7.5 (the
    --accept-changes flag stabilized in 7.5). On macOS, soffice may live
    at /Applications/LibreOffice.app/... or /opt/homebrew/bin/soffice; on
    Linux it is /usr/bin/soffice. Returns {ok, path, version, message}.
    """
    path = shutil.which("soffice")
    if path is None:
        for cand in (SOFFICE_MAC_CANONICAL, SOFFICE_LINUX_CANONICAL, SOFFICE_BREW):
            if Path(cand).exists():
                path = cand
                break
    if path is None:
        if sys.platform == "darwin":
            install = "brew install --cask libreoffice"
        else:
            install = "apt-get install -y libreoffice"
        return {
            "ok": False,
            "path": None,
            "version": None,
            "message": (
                "security-compliance: soffice (LibreOffice) not found; "
                f"--accept-changes will fail. Install with: {install}"
            ),
        }
    try:
        proc = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            cwd=SAFE_CWD,
            env=safe_subprocess_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "path": path,
            "version": None,
            "message": f"security-compliance: soffice version probe failed: {exc}",
        }
    version_line = (proc.stdout or "").strip().splitlines()[:1]
    version_str = version_line[0] if version_line else ""
    parts = version_str.split()
    version_tuple: tuple[int, ...] = ()
    for part in parts:
        digits = part.split(".")
        if len(digits) >= 2 and all(d.isdigit() for d in digits[:2]):
            version_tuple = (int(digits[0]), int(digits[1]))
            break
    if version_tuple and version_tuple < SOFFICE_MIN_VERSION:
        return {
            "ok": False,
            "path": path,
            "version": version_str,
            "message": (
                f"security-compliance: soffice {version_str} is below "
                f"{'.'.join(str(v) for v in SOFFICE_MIN_VERSION)}; "
                "--accept-changes may behave inconsistently."
            ),
        }
    return {
        "ok": True,
        "path": path,
        "version": version_str,
        "message": f"security-compliance: soffice OK ({version_str})",
    }


def main() -> None:
    """Probe-then-install. Always exits 0."""
    try:
        if not python_docx_available():
            result = install_python_docx()
            emit(result["message"])
        soffice_result = _probe_soffice()
        if not soffice_result["ok"]:
            emit(soffice_result["message"])
    except Exception as exc:
        try:
            emit("security-compliance dependency check error: %s" % str(exc))
        except Exception:
            pass


if __name__ == "__main__":
    main()
    sys.exit(0)
