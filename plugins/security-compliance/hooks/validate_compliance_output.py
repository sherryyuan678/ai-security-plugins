#!/usr/bin/env python3
"""PostToolUse hook: validate compliance report files as they are written.

Reads JSON from stdin (PostToolUse event payload), checks whether the
written file is inside a .compliance-check/ or .compliance-reports/
directory, and if so runs deterministic validation checks via
scripts/validate_report.py.

Always exits 0.  This hook is strictly informational — it never blocks
the report.
"""

from __future__ import annotations

import json
import os
import sys


def main():
    # type: () -> None
    try:
        # Add plugin root and scripts dir to sys.path for imports
        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
        if plugin_root:
            if plugin_root not in sys.path:
                sys.path.insert(0, plugin_root)
            scripts_dir = os.path.join(plugin_root, "scripts")
            if scripts_dir not in sys.path:
                sys.path.insert(0, scripts_dir)

        raw = sys.stdin.read()
        if not raw.strip():
            return

        try:
            event = json.loads(raw)
        except (ValueError, TypeError):
            return

        tool_name = event.get("tool_name", "")
        tool_input = event.get("tool_input", {})
        if not isinstance(tool_input, dict):
            return

        # Determine file path and content based on tool type
        if tool_name == "Write":
            file_path = tool_input.get("file_path", "")
            content = tool_input.get("content", "")
        elif tool_name in ("Edit", "MultiEdit"):
            file_path = tool_input.get("file_path", "")
            # Edit/MultiEdit: the file has already been written to disk by the
            # time PostToolUse fires, so read the full file for validation
            # rather than validating just the replacement fragment.
            try:
                with open(file_path, "r", encoding="utf-8") as fh:
                    content = fh.read()
            except (IOError, OSError):
                # File unreadable — degrade gracefully, skip validation
                return
        else:
            return

        # Gate: only act on .compliance-check/ and .compliance-reports/ files
        is_compliance_check = (
            ".compliance-check/" in file_path or ".compliance-check\\" in file_path
        )
        is_compliance_report = (
            ".compliance-reports/" in file_path or ".compliance-reports\\" in file_path
        )
        if not is_compliance_check and not is_compliance_report:
            return

        # Extract filename from path
        filename = os.path.basename(file_path)

        # state.json is only written by /security-compliance:compliance-check.
        # Spot-check files in .compliance-reports/ must NOT load state.json:
        # a stale state from a prior compliance-check run would override the
        # spot-check's own frontmatter scope and flag legitimate in-scope
        # mentions as violations. validate_compliance_file synthesizes the
        # allow-list from ``applicable_frameworks`` frontmatter when state is
        # None.
        # ``is_compliance_check`` and ``is_compliance_report`` are substring
        # tests, so a path like ``.compliance-reports/.compliance-check/foo.md``
        # would set both flags. Prefer report semantics in that case so a stale
        # state.json never overrides a report-bearing path's frontmatter.
        cwd = event.get("cwd", "")
        state = None
        if cwd and is_compliance_check and not is_compliance_report:
            state_path = os.path.join(cwd, ".compliance-check", "state.json")
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
            except (IOError, OSError, ValueError):
                pass

        # Import validation module
        from scripts.validate_report import validate_compliance_file

        result = validate_compliance_file(content, filename, state)

        # Build system message from results
        messages = []  # type: list

        for item in result.get("scope_violations", []):
            messages.append("- Scope: %s" % item)

        for item in result.get("info", []):
            messages.append("- %s" % item)

        for item in result.get("warnings", []):
            messages.append("- %s" % item)

        if messages:
            header = "Compliance validation (%s):" % filename
            body = "\n".join(messages)
            output = {"systemMessage": "%s\n%s" % (header, body)}
            print(json.dumps(output))

    except Exception as exc:
        # Never crash — surface the error as a system message and exit 0
        try:
            output = {
                "systemMessage": "Compliance validation hook error: %s" % str(exc),
            }
            print(json.dumps(output))
        except Exception:
            pass


if __name__ == "__main__":
    main()
    sys.exit(0)
