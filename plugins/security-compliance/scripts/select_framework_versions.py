#!/usr/bin/env python3
"""Resolve nearest applicable framework versions for an as-of date."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List

DISPLAY_NAMES = {
    "SOC2": "SOC 2",
    "ISO_27001": "ISO 27001",
    "PCI_DSS": "PCI DSS",
    "EU_AI_ACT": "EU AI Act",
    "CCPA_CPRA": "CCPA/CPRA",
    "NIST_CSF": "NIST CSF",
}


def parse_date(value: str) -> dt.date:
    """Parse YYYY-MM-DD or the literal ``auto`` (current UTC date)."""
    if value == "auto":
        return dt.datetime.now(dt.timezone.utc).date()
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def load_index(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_framework_args(raw_values: List[str]) -> List[str]:
    items: List[str] = []
    for val in raw_values:
        parts = [p.strip() for p in val.split(",") if p.strip()]
        items.extend(parts)
    return items


def resolve_framework(versions: List[Dict[str, Any]], as_of: dt.date) -> Dict[str, Any]:
    enriched = []
    for item in versions:
        item_date = parse_date(item["effective_date"])
        enriched.append((item_date, item))
    enriched.sort(key=lambda x: x[0])

    past_or_now = [x for x in enriched if x[0] <= as_of]
    future = [x for x in enriched if x[0] > as_of]

    if past_or_now:
        eff_date, selected = past_or_now[-1]
        basis = "latest_effective_not_after_as_of"
        status = "resolved"
    elif future:
        eff_date, selected = future[0]
        basis = "nearest_future_effective"
        status = "pre_effective"
    else:
        return {"status": "unresolved", "reason": "no_versions_in_index"}

    delta_days = (as_of - eff_date).days
    output = dict(selected)
    output["status"] = status
    output["resolution_basis"] = basis
    output["effective_date_delta_days"] = delta_days
    return output


def as_markdown(result: Dict[str, Any]) -> str:
    lines = []
    lines.append(f"# Framework Snapshot (as-of {result['as_of_date']})")
    lines.append("")
    lines.append(
        "| Framework | Version | Effective Date | Publication Date | Basis | Source |"
    )
    lines.append("|---|---|---|---|---|---|")
    for name, details in result["frameworks"].items():
        display = DISPLAY_NAMES.get(name, name)
        status = details.get("status")
        if status == "unresolved":
            lines.append(
                f"| {display} | UNRESOLVED | - | - | {details.get('reason', '-')} | - |"
            )
            continue
        version = details.get("version", "-")
        eff = details.get("effective_date", "-")
        pub = details.get("publication_date", "-")
        basis = details.get("resolution_basis", "-")
        source = details.get("source_url", "-")
        if status == "pre_effective":
            basis = f"{basis} (pre-effective)"
        lines.append(f"| {display} | {version} | {eff} | {pub} | {basis} | {source} |")
    return "\n".join(lines)


def resolve_index_path(explicit: str | None) -> Path:
    """Locate the framework_index.json with three levels of fallback.

    1. ``explicit`` — what the caller passed via ``--index`` (highest priority).
    2. Script-relative ``<plugin_root>/data/framework_index.json`` — works when
       the script is invoked from any cwd, including the repo root.
    3. Legacy cwd-relative ``data/framework_index.json`` — preserves behavior
       for callers that already pin cwd to the plugin dir.
    """
    if explicit:
        return Path(explicit)
    script_relative = (
        Path(__file__).resolve().parent.parent / "data" / "framework_index.json"
    )
    if script_relative.exists():
        return script_relative
    return Path("data/framework_index.json")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve framework versions by as-of date."
    )
    parser.add_argument(
        "--as-of",
        required=True,
        help="As-of date in YYYY-MM-DD format, or the literal 'auto' for current UTC date.",
    )
    parser.add_argument(
        "--index",
        default=None,
        help="Path to framework index JSON. If omitted, the script falls back to "
        "<plugin_root>/data/framework_index.json relative to this file, then "
        "to data/framework_index.json relative to cwd.",
    )
    parser.add_argument(
        "--framework",
        action="append",
        default=[],
        help="Framework name(s), repeatable or comma-separated. Default is all.",
    )
    parser.add_argument(
        "--format", choices=["json", "markdown"], default="json", help="Output format."
    )
    args = parser.parse_args()

    as_of = parse_date(args.as_of)
    resolved_as_of = as_of.strftime("%Y-%m-%d")
    index_path = resolve_index_path(args.index)
    data = load_index(index_path)
    frameworks = data.get("frameworks", {})

    requested = normalize_framework_args(args.framework)
    names = requested if requested else sorted(frameworks.keys())

    result: Dict[str, Any] = {
        "as_of_date": resolved_as_of,
        "resolved_at_utc": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "index_path": str(index_path),
        "frameworks": {},
    }

    for name in names:
        versions = frameworks.get(name)
        if not versions:
            result["frameworks"][name] = {
                "status": "unresolved",
                "reason": "framework_not_found",
            }
            continue
        result["frameworks"][name] = resolve_framework(versions, as_of)

    if args.format == "markdown":
        print(as_markdown(result))
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
