#!/usr/bin/env python3
"""PostToolUse hook: re-validate any DOCX written into a *.versions/ path.

Reads JSON from stdin per Claude Code's hook protocol. Emits a systemMessage
on stdout if validation fails. Always exits 0 (informs, never blocks).

Soft-fail per the plugin's existing convention. Audit fix MEDIUM 13:
the script self-scopes to *.versions/*.docx via fnmatch.
"""

from __future__ import annotations

import fnmatch
import json
import sys
from pathlib import Path


def _emit_system_message(text: str) -> None:
    print(json.dumps({"systemMessage": text}))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return 0

    file_path = payload.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return 0

    if not fnmatch.fnmatch(file_path, "*.versions/*.docx"):
        return 0

    sys.path.insert(
        0, str(Path(__file__).resolve().parent.parent / "scripts")
    )
    try:
        from _docx_validate import validate_edited_docx
        report = validate_edited_docx(file_path)
    except Exception as exc:  # noqa: BLE001
        _emit_system_message(
            f"validate_edited_docx hook failed to import/run: "
            f"{type(exc).__name__}: {exc}"
        )
        return 0

    if not report.ok:
        failed = [s for s in report.stages if s.status == "fail"]
        _emit_system_message(
            f"PostToolUse: {file_path} failed validation. "
            f"Failures: {[(s.name, s.reason) for s in failed]}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
