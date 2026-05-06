#!/usr/bin/env python3
"""UserPromptSubmit hook: auto-resolve framework versions for compliance prompts.

When the user's prompt mentions compliance-related keywords, resolves
current framework versions from the plugin's data index and injects
them into Claude's context via the additionalContext field.

Always exits 0.  Never blocks the user's prompt.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys


COMPLIANCE_KEYWORDS = re.compile(
    r"\b(compliance|gdpr|hipaa|soc.?2|pci.?dss|ccpa|cpra|dora"
    r"|iso.?27001|nist|audit|regulatory|eu.?ai.?act|cmmc|fedramp)\b",
    re.IGNORECASE,
)

AS_OF_RE = re.compile(r"--as-of\s+(\d{4}-\d{2}-\d{2}|auto)")


def extract_as_of(prompt: str) -> str:
    """Pull --as-of YYYY-MM-DD from a slash-command prompt.

    Returns the matched date when valid, or today's UTC date when:
    - no --as-of is present in the prompt;
    - the matched value is the literal "auto" (documented contract);
    - the matched value parses but is malformed (the hook coerces to
      today silently rather than crashing; the resolver is then called
      with that coerced value, not the malformed one).

    The injected context targets the same date the slash-command will
    use when it (re)invokes the resolver, keeping --strict-facts honest
    on well-formed inputs. Malformed inputs are swallowed by design;
    surfacing them belongs to the slash command, not the hook.
    """
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    match = AS_OF_RE.search(prompt)
    if not match:
        return today
    value = match.group(1)
    if value == "auto":
        return today
    try:
        datetime.datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return today
    return value


def main():
    # type: () -> None
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return

        try:
            event = json.loads(raw)
        except (ValueError, TypeError):
            return

        prompt = event.get("prompt", "")
        if not prompt:
            return

        # Gate: only run when compliance keywords are present
        if not COMPLIANCE_KEYWORDS.search(prompt):
            return

        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
        if not plugin_root:
            return

        script_path = os.path.join(
            plugin_root,
            "scripts",
            "select_framework_versions.py",
        )
        index_path = os.path.join(
            plugin_root,
            "data",
            "framework_index.json",
        )

        if not os.path.isfile(script_path):
            return

        as_of = extract_as_of(prompt)

        try:
            proc = subprocess.run(
                [
                    "python3",
                    script_path,
                    "--as-of",
                    as_of,
                    "--index",
                    index_path,
                    "--format",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=8,
            )
        except (OSError, subprocess.TimeoutExpired):
            return

        if proc.returncode != 0:
            return

        framework_data = proc.stdout.strip()
        if not framework_data:
            return

        output = {
            "additionalContext": (
                "Current regulatory framework versions "
                "(auto-resolved from plugin data):\n%s" % framework_data
            ),
        }
        print(json.dumps(output))

    except Exception:
        # Never crash — silently degrade and exit 0
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
