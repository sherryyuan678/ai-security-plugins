#!/usr/bin/env python3
"""Compliance report validation library.

Deterministic checks for scope discipline, terminology consistency,
required sections, and hallucination markers.  Extracted from the
assertion-matching logic in run_eval.py.

Usage as library:
    from scripts.validate_report import validate_compliance_file

Usage as CLI:
    python3 scripts/validate_report.py --file <path> [--state <path>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys

# Referenced via Python 2-style ``# type:`` comments below.
from typing import Any, Dict, List, Optional  # noqa: F401

from matching import (
    canonical_for,
    contains_forbidden_with_context,
)

STANDARD_ABBREVIATIONS = {
    "SOC 2": [r"\bSOC-2\b", r"\bSOC2\b(?!\s+Type)"],
    "ISO 27001": [r"\bISO27001\b", r"\bISO-27001\b"],
    "PCI DSS": [r"\bPCI-DSS\b", r"\bPCIDSS\b"],
    "NIST CSF": [r"\bNIST-CSF\b"],
    "CCPA/CPRA": [r"\bCCPA-CPRA\b"],
}  # type: Dict[str, List[str]]

REQUIRED_SECTIONS = {
    "01-applicability.md": [
        "Regulatory Applicability Assessment",
    ],
    "02-control-map.md": [
        "Cross-Framework Control",
    ],
    "03-gap-analysis.md": [
        "Compliance Gap",
    ],
    "04-roadmap.md": [
        "Implementation Roadmap",
    ],
    "05-technical-controls.md": [
        "Technical Control",
    ],
    "06-policy-templates.md": [
        "Policy",
    ],
    "07-audit-package.md": [
        "Audit",
    ],
    "08-evidence-ledger.md": [
        "Evidence",
    ],
}  # type: Dict[str, List[str]]

SPOT_CHECK_REQUIRED_SECTIONS = [
    "TL;DR",
    "Regulatory Applicability Assessment",
    "Compliance Gap Summary",
    "Cross-Framework Control Map",
    "Recommended Next Steps",
]  # type: List[str]

SPOT_CHECK_FILENAME_RE = re.compile(r"^spot-check-\d{4}-\d{2}-\d{2}.*\.md$")

ALL_KNOWN_FRAMEWORKS = [
    "GDPR",
    "HIPAA",
    "SOC 2",
    "PCI DSS",
    "ISO 27001",
    "NIST CSF",
    "CCPA/CPRA",
    "DORA",
    "EU AI Act",
    "CMMC",
    "FedRAMP",
]  # type: List[str]


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_KEY_INLINE_RE = re.compile(
    r'^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?:"([^"]*)"|(\S.*?))\s*$'
)
_KEY_BLOCK_HEADER_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*$")
_LIST_ITEM_RE = re.compile(r"^\s+-\s+(?:\"([^\"]*)\"|(\S.*?))\s*$")


def _canonical_set(applicable):
    # type: (List[str]) -> set[str]
    """Map ``applicable_frameworks`` entries onto canonical lowercase keys.

    The resolver in ``select_framework_versions.py`` emits JSON keys with
    underscore separators (``ISO_27001``, ``PCI_DSS``, ``CCPA_CPRA``,
    ``NIST_CSF``, ``EU_AI_ACT``) which do not appear in
    ``FRAMEWORK_ALIASES``. To bridge resolver-format keys onto the same
    canonical bucket as display-form names, try the raw form first, then
    the underscore-to-space form (covers ``iso_27001`` → ``iso 27001``),
    then the underscore-to-slash form (covers ``ccpa_cpra`` → ``ccpa/cpra``).

    Unknown entries are kept as their underscore-to-space form so a
    user's declared framework is still treated as in-scope and matches
    the lowercased ``ALL_KNOWN_FRAMEWORKS`` display names.
    """
    canonical = set()  # type: set[str]
    for raw in applicable:
        item = str(raw).strip().lower()
        if not item:
            continue
        result = (
            canonical_for(item)
            or canonical_for(item.replace("_", " "))
            or canonical_for(item.replace("_", "/"))
        )
        if result:
            canonical.add(result)
            continue
        fallback = item.replace("_", " ").strip()
        if fallback:
            canonical.add(fallback)
    return canonical


def parse_frontmatter(content):
    # type: (str) -> Dict[str, Any]
    """Parse the limited YAML shapes used by the spot-check template.

    Deliberately a regex mini-parser rather than PyYAML — the plugin must
    not add a runtime dependency just to read three frontmatter shapes.

    Supports:
        key: value            -> str
        key: "value"          -> str (quotes stripped)
        key:                  -> list[str]
          - item
          - "item with spaces"

    Anything else (nested mappings, flow lists, anchors) is ignored. The
    return value is a flat ``dict[str, str | list[str]]``; callers must
    treat it as such, not as a full YAML structure.
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}
    block = match.group(1)
    lines = block.splitlines()
    result = {}  # type: Dict[str, Any]
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        inline = _KEY_INLINE_RE.match(line)
        if inline:
            key = inline.group(1)
            quoted = inline.group(2)
            unquoted = inline.group(3)
            value = quoted if quoted is not None else (unquoted or "").strip()
            result[key] = value
            i += 1
            continue
        block_header = _KEY_BLOCK_HEADER_RE.match(line)
        if block_header:
            key = block_header.group(1)
            items = []  # type: List[str]
            j = i + 1
            while j < len(lines):
                item_match = _LIST_ITEM_RE.match(lines[j])
                if not item_match:
                    break
                quoted = item_match.group(1)
                unquoted = item_match.group(2)
                item = quoted if quoted is not None else (unquoted or "").strip()
                items.append(item)
                j += 1
            result[key] = items
            i = j
            continue
        i += 1
    return result


# ---------------------------------------------------------------------------
# Additional validation functions
# ---------------------------------------------------------------------------


def check_terminology(text):
    # type: (str) -> List[Dict[str, str]]
    """Return list of {found, preferred} for non-standard abbreviations."""
    issues = []  # type: List[Dict[str, str]]
    for preferred, patterns in STANDARD_ABBREVIATIONS.items():
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                issues.append({"found": match, "preferred": preferred})
    return issues


def _strip_code_fences(text):
    # type: (str) -> str
    """Remove fenced code blocks (``` or ~~~) so headings inside them
    don't satisfy section-presence checks.

    Tracks fence state line-by-line and toggles on any line that begins
    (after up to three spaces of CommonMark indentation) with a fence
    marker. Imperfect for nested or weirdly-balanced fences but adequate
    for compliance reports.
    """
    lines = text.split("\n")
    keep = []  # type: List[str]
    in_fence = False
    for line in lines:
        stripped = line.lstrip(" ")
        if len(line) - len(stripped) <= 3 and (
            stripped.startswith("```") or stripped.startswith("~~~")
        ):
            in_fence = not in_fence
            continue
        if not in_fence:
            keep.append(line)
    return "\n".join(keep)


def check_required_sections(text, filename):
    # type: (str, str) -> List[str]
    """Return list of missing required section headings for the given file.

    Spot-check files (matching ``SPOT_CHECK_FILENAME_RE``) get the
    spot-check checklist; multi-phase compliance-check files get the
    REQUIRED_SECTIONS entry for their basename.

    Headings are matched per-line with the CommonMark form
    ``^[ ]{0,3}#{1,6}\\s+<heading>(?=[^A-Za-z0-9_-]|$)``, so:

    - A Table-of-Contents link (``- [TL;DR](#tldr)``) does not satisfy
      the check; only an actual ``## TL;DR`` heading does.
    - Heading levels h1 through h6 are all accepted.
    - A heading like ``## Compliance Gap-Notes`` does NOT satisfy
      ``Compliance Gap`` (the hyphen makes it a different name).
    - A heading like ``## Compliance Gap Summary`` DOES satisfy the
      ``Compliance Gap`` prefix entry from REQUIRED_SECTIONS.
    - Frontmatter and fenced code blocks are stripped first so YAML
      comments and code-block headings don't false-positive.
    """
    if SPOT_CHECK_FILENAME_RE.match(filename):
        expected = SPOT_CHECK_REQUIRED_SECTIONS
    else:
        expected = REQUIRED_SECTIONS.get(filename, [])
    if not expected:
        return []
    frontmatter_match = _FRONTMATTER_RE.match(text)
    body = text[frontmatter_match.end() :] if frontmatter_match else text
    body = _strip_code_fences(body)
    missing = []  # type: List[str]
    for heading in expected:
        pattern = (
            r"^[ ]{0,3}#{1,6}[ \t]+" + re.escape(heading) + r"(?=[^A-Za-z0-9_-]|$)"
        )
        if not re.search(pattern, body, re.MULTILINE | re.IGNORECASE):
            missing.append(heading)
    return missing


def count_markers(text):
    # type: (str) -> Dict[str, int]
    """Count REQUIRES VALIDATION and UNVERIFIED markers."""
    rv_count = len(re.findall(r"REQUIRES\s+VALIDATION", text, re.IGNORECASE))
    uv_count = len(re.findall(r"\bUNVERIFIED\b", text, re.IGNORECASE))
    return {"requires_validation": rv_count, "unverified": uv_count}


def validate_compliance_file(
    content,  # type: str
    filename,  # type: str
    state=None,  # type: Optional[Dict[str, Any]]
):
    # type: (...) -> Dict[str, Any]
    """Run all validation checks on a compliance output file.

    Args:
        content: The file content to validate.
        filename: The basename of the file (e.g. "01-applicability.md").
        state: Parsed .compliance-check/state.json, or None.

    Returns:
        Dictionary with warnings, info, scope_violations, and
        terminology_issues lists.
    """
    warnings = []  # type: List[str]
    info = []  # type: List[str]
    scope_violations = []  # type: List[str]
    terminology_issues = check_terminology(content)

    # Hallucination marker counts
    markers = count_markers(content)
    if markers["requires_validation"] > 0:
        info.append(
            "%d REQUIRES VALIDATION marker(s) found" % markers["requires_validation"]
        )
    if markers["unverified"] > 0:
        info.append("%d UNVERIFIED marker(s) found" % markers["unverified"])

    # Required section check
    missing_sections = check_required_sections(content, filename)
    for section in missing_sections:
        warnings.append("Missing expected section: %s" % section)

    # Spot-check files have no .compliance-check/state.json; synthesize
    # the scope allow-list from their own ``applicable_frameworks``
    # frontmatter and run with strict_mode so exclusion phrases don't
    # silently swallow out-of-scope mentions.
    is_spot_check = bool(SPOT_CHECK_FILENAME_RE.match(filename))
    if state is None and is_spot_check:
        frontmatter = parse_frontmatter(content)
        applicable = frontmatter.get("applicable_frameworks")
        if isinstance(applicable, list) and applicable:
            state = {"selected_frameworks": applicable}

    if state is not None:
        selected = state.get("selected_frameworks", [])
        selected_canonical = _canonical_set(selected)
        excluded = [
            f for f in ALL_KNOWN_FRAMEWORKS if f.lower() not in selected_canonical
        ]
        if excluded:
            hits, _ignored = contains_forbidden_with_context(
                content,
                excluded,
                strict_mode=is_spot_check,
            )
            for hit in hits:
                scope_violations.append(
                    "Out-of-scope framework mentioned outside exclusion "
                    "context: %s" % hit
                )

    # Terminology issues as warnings
    for issue in terminology_issues:
        warnings.append(
            "Terminology: found '%s', prefer '%s'"
            % (issue["found"], issue["preferred"])
        )

    return {
        "warnings": warnings,
        "info": info,
        "scope_violations": scope_violations,
        "terminology_issues": terminology_issues,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main():
    # type: () -> None
    parser = argparse.ArgumentParser(
        description="Validate a compliance report file.",
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to the compliance file to validate.",
    )
    parser.add_argument(
        "--state",
        default=None,
        help="Path to .compliance-check/state.json (optional).",
    )
    args = parser.parse_args()

    try:
        with open(args.file, "r", encoding="utf-8") as f:
            content = f.read()
    except (IOError, OSError) as exc:
        result = {"error": "Cannot read file: %s" % str(exc)}
        print(json.dumps(result, indent=2))
        sys.exit(1)

    state = None  # type: Optional[Dict[str, Any]]
    if args.state:
        try:
            with open(args.state, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (IOError, OSError, ValueError) as exc:
            result = {"error": "Cannot read state file: %s" % str(exc)}
            print(json.dumps(result, indent=2))
            sys.exit(1)

    import os

    filename = os.path.basename(args.file)
    result = validate_compliance_file(content, filename, state)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
