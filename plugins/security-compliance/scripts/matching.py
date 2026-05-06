#!/usr/bin/env python3
"""Shared alias maps, exclusion patterns, and matching functions.

Used by both run_eval.py (assertion scoring) and validate_report.py
(hook-time validation) to ensure consistent matching behaviour.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Framework naming variants for expected-framework assertions
# ---------------------------------------------------------------------------

FRAMEWORK_ALIASES: Dict[str, List[str]] = {
    "soc 2": ["soc2", "soc-2", "soc 2 type ii", "soc2 type ii", "soc 2 type i"],
    "ccpa/cpra": [
        "ccpa",
        "cpra",
        "california privacy rights act",
        "california consumer privacy act",
    ],
    "nist csf": [
        "nist cybersecurity framework",
        "nist csf 2.0",
        "csf 2.0",
        "nist sp 800-53",
        "nist 800-53",
        "nist sp 800-53 rev. 5",
        "nist sp 800-53 rev 5",
    ],
    "iso 27001": ["iso/iec 27001", "iso27001", "iso-27001", "iso 27001:2022"],
    "fedramp": ["fed-ramp", "fed ramp"],
    "cmmc": ["cybersecurity maturity model certification"],
}

# ---------------------------------------------------------------------------
# Canonical must_include assertions and common semantic variants
# ---------------------------------------------------------------------------

MUST_INCLUDE_ALIASES: Dict[str, List[str]] = {
    "regulatory applicability assessment": [
        "applicability assessment",
        "regulatory assessment",
    ],
    "compliance gap analysis": [
        "gap analysis",
        "framework gap analysis",
        "compliance gaps",
    ],
    "cross-framework control map": [
        "cross-framework control mapping",
        "cross-framework mapping",
        "control mapping matrix",
        "unified control mapping",
        "control mapping",
    ],
    "prioritized implementation roadmap": [
        "implementation roadmap",
        "prioritized roadmap",
        "compliance roadmap",
        "implementation plan",
    ],
    "audit preparation package": [
        "audit package",
        "audit readiness package",
        "audit readiness",
        "audit preparation",
    ],
    "ict risk management": [
        "ict risk",
        "technology risk management",
        "ict risk framework",
        "ict risk governance",
    ],
    "incident reporting": [
        "incident notification",
        "reporting incidents",
        "incident report",
    ],
    "resilience testing": [
        "operational resilience testing",
        "resilience test",
        "threat-led penetration testing",
        "tlpt",
        "digital operational resilience testing",
    ],
    "third-party ict risk": [
        "third party ict risk",
        "third-party risk",
        "vendor ict risk",
        "third-party ict",
        "ict third-party",
    ],
    "single implementation": [
        "single-implementation",
        "one implementation",
        "unified implementation",
        "unified control implementation",
        "consolidated implementation",
        "common control",
        "shared control",
    ],
    "duplicate effort": [
        "duplicative effort",
        "effort duplication",
        "redundancy",
        "duplicate controls",
        "overlapping controls",
        "eliminate overlap",
        "reduce redundancy",
        "redundant controls",
        "control overlap",
    ],
    "data subject rights": [
        "data subject requests",
        "dsr rights",
        "right to erasure",
        "right to access",
        "data rights",
    ],
    "vendor management": [
        "vendor risk management",
        "third-party management",
        "third-party risk management",
        "vendor oversight",
        "supply chain risk",
    ],
    "incident response": [
        "security incident response",
        "breach response",
        "incident response plan",
        "breach notification",
    ],
    "audit logging": [
        "access logging",
        "audit trail",
        "centralized logging",
        "audit log",
    ],
    "risk-based justification": [
        "risk-proportionate",
        "justified by risk",
        "proportionate to risk",
        "risk-based approach",
        "risk assessment justif",
    ],
    "retention schedule": [
        "retention policy",
        "data retention schedule",
        "retention period",
        "data retention policy",
    ],
    "regulatory timeline harmonization": [
        "timeline harmonization",
        "harmonized timeline",
        "notification timeline",
        "aligned timelines",
        "reconcile.*timeline",
        "timeline alignment",
        "reporting timeline",
    ],
    "no restricted cross-border transfer": [
        "no cross-border transfer",
        "no restricted transfer",
        "no transfer mechanism required",
        "intra-eu",
        "within the eu",
        "data remains within",
    ],
    "transfer register": [
        "transfer log",
        "record of transfers",
        "transfer documentation",
        "transfer record",
    ],
}

# ---------------------------------------------------------------------------
# Exclusion-context patterns (negative statements that mention frameworks)
# ---------------------------------------------------------------------------

EXCLUSION_CONTEXT_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"\bnot\s+applicable\b", re.IGNORECASE),
    re.compile(r"\bnot\s+in\s+scope\b", re.IGNORECASE),
    re.compile(r"\bout\s+of\s+scope\b", re.IGNORECASE),
    re.compile(r"\bdoes\s+not\s+apply\b", re.IGNORECASE),
    re.compile(r"\bexcluded?\b", re.IGNORECASE),
    re.compile(r"\bexclusion\b", re.IGNORECASE),
    re.compile(r"\bonly\s+if\b", re.IGNORECASE),
    re.compile(
        r"\bno\s+(?:eu|phi|payment|cardholder|financial|federal|government"
        r"|defense)\b",
        re.IGNORECASE,
    ),
)


# ---------------------------------------------------------------------------
# Matching functions
# ---------------------------------------------------------------------------


def _term_candidates(
    raw_item: Any,
    alias_map: Optional[Dict[str, List[str]]],
) -> Tuple[str, List[str]]:
    """Resolve a term and its aliases from a raw item and an alias map."""
    if isinstance(raw_item, dict):
        term = str(raw_item.get("term", "")).strip()
        raw_aliases = raw_item.get("aliases", [])
        item_aliases = [str(a).strip() for a in raw_aliases if str(a).strip()]
    else:
        term = str(raw_item).strip()
        item_aliases = []

    if not term:
        return "", []

    global_aliases = (alias_map or {}).get(term.lower(), [])
    merged = item_aliases + global_aliases

    deduped: List[str] = []
    seen: set[str] = set()
    for candidate in merged:
        low = candidate.lower()
        if low in seen:
            continue
        seen.add(low)
        deduped.append(candidate)

    return term, deduped


def contains_all(
    text: str,
    checks: Iterable[Any],
    alias_map: Optional[Dict[str, List[str]]] = None,
) -> Tuple[List[str], List[str]]:
    """Check whether all expected items appear in text (with alias expansion).

    Returns (found, missing) lists.
    """
    found: List[str] = []
    missing: List[str] = []
    lower = text.lower()
    for raw_item in checks:
        item, aliases = _term_candidates(raw_item, alias_map)
        if not item:
            continue
        candidates = [item] + aliases
        if any(candidate.lower() in lower for candidate in candidates):
            found.append(item)
        else:
            missing.append(item)
    return found, missing


def contains_any(text: str, checks: Iterable[Any]) -> List[str]:
    """Return list of items from *checks* that appear in *text*."""
    lower = text.lower()
    hits: List[str] = []
    for raw_item in checks:
        item = str(raw_item).strip()
        if item and item.lower() in lower:
            hits.append(item)
    return hits


_PARAGRAPH_LOOKBACK_CAP = 10


def _is_paragraph_boundary(line: str) -> bool:
    """A blank line or a markdown heading marks a paragraph break."""
    stripped = line.strip()
    if not stripped:
        return True
    return stripped.startswith("#")


def is_exclusion_context(lines: List[str], idx: int, strict_mode: bool = False) -> bool:
    """Return True if the line at *idx* is within exclusion context.

    ``strict_mode=True`` disables the bypass entirely (used by spot-check
    where "no out-of-scope names anywhere" is absolute). Otherwise scan
    backward for the current paragraph start (a blank line or markdown
    heading) within a 10-line cap; fall back to the previous 2 lines if
    no boundary is found.
    """
    if strict_mode:
        return False
    cap = max(0, idx - _PARAGRAPH_LOOKBACK_CAP)
    start = idx
    boundary_found = False
    while start > cap:
        candidate = start - 1
        if _is_paragraph_boundary(lines[candidate]):
            start = candidate + 1
            boundary_found = True
            break
        start = candidate
    if not boundary_found:
        start = max(0, idx - 2)
    context_window = "\n".join(lines[start : idx + 1])
    return any(pattern.search(context_window) for pattern in EXCLUSION_CONTEXT_PATTERNS)


def _build_reverse_alias_index() -> Dict[str, str]:
    """Build a single-pass alias→canonical map at import time.

    Wrapped in a function so the loop variables don't leak into the
    module namespace.
    """
    index: Dict[str, str] = {canon: canon for canon in FRAMEWORK_ALIASES}
    for canon, aliases in FRAMEWORK_ALIASES.items():
        for alias in aliases:
            index[alias.lower()] = canon
    return index


_REVERSE_ALIAS_INDEX: Dict[str, str] = _build_reverse_alias_index()


def canonical_for(item: str) -> Optional[str]:
    """Return the canonical lowercase key for *item*, or None if unknown.

    Recognizes both canonical names ("soc 2") and any alias listed under
    them in ``FRAMEWORK_ALIASES``. Backed by a precomputed reverse index
    so per-call cost is O(1).
    """
    return _REVERSE_ALIAS_INDEX.get(item.strip().lower())


def _alias_needles(item: str) -> List[str]:
    """Return the lowercase needle set for a forbidden framework name.

    The canonical name is always included as one of its own needles. When
    the item is unknown, a one-element list with the lowercased item is
    returned, preserving the pre-A6 default behavior for callers passing
    arbitrary strings.
    """
    canon = canonical_for(item)
    if canon is None:
        return [item.strip().lower()]
    seen: set[str] = {canon}
    needles: List[str] = [canon]
    for alias in FRAMEWORK_ALIASES[canon]:
        low = alias.lower()
        if low in seen:
            continue
        seen.add(low)
        needles.append(low)
    return needles


def contains_forbidden_with_context(
    text: str,
    checks: Iterable[Any],
    strict_mode: bool = False,
) -> Tuple[List[str], List[str]]:
    """Check for forbidden items with context-aware exclusion filtering.

    Returns (hits, ignored) where *hits* are true violations and *ignored*
    are mentions that appeared only in exclusion context. ``strict_mode``
    disables the exclusion-context bypass and is paired with paragraph-
    bounded scanning in :func:`is_exclusion_context`. Forbidden names are
    expanded via :data:`FRAMEWORK_ALIASES` so a bare "CCPA" is flagged
    when "CCPA/CPRA" is the canonical entry.
    """
    lower_lines = text.lower().splitlines()

    hits: List[str] = []
    ignored: List[str] = []
    for raw_item in checks:
        item = str(raw_item).strip()
        if not item:
            continue
        needles = _alias_needles(item)
        matched_any_context = False
        matched_exclusion_only = True

        for idx, line in enumerate(lower_lines):
            if not any(needle in line for needle in needles):
                continue
            matched_any_context = True
            if is_exclusion_context(lower_lines, idx, strict_mode=strict_mode):
                continue
            matched_exclusion_only = False
            hits.append(item)
            break

        if matched_any_context and matched_exclusion_only:
            ignored.append(item)

    return hits, ignored
