#!/usr/bin/env python3
"""Build a markdown evidence ledger from JSONL claim entries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def load_claims(path: Path) -> List[Dict[str, Any]]:
    claims: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            claims.append(json.loads(line))
    return claims


def render_markdown(claims: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    lines.append("# Evidence Ledger")
    lines.append("")
    lines.append("| Claim | Framework | Source URL | Publication Date | Effective Date | Retrieved Date | Confidence |")
    lines.append("|---|---|---|---|---|---|---|")
    for c in claims:
        claim = str(c.get("claim", "")).replace("\n", " ").strip()
        framework = str(c.get("framework", "-"))
        source = str(c.get("source_url", "-"))
        pub_date = str(c.get("publication_date", "-"))
        eff_date = str(c.get("effective_date", "-"))
        retrieved = str(c.get("retrieved_date", "-"))
        confidence = str(c.get("confidence", "UNVERIFIED"))
        lines.append(
            f"| {claim} | {framework} | {source} | {pub_date} | {eff_date} | {retrieved} | {confidence} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Create evidence ledger markdown from JSONL claims.")
    parser.add_argument("--claims-file", required=True, help="JSONL file with claim rows.")
    parser.add_argument("--out", default="08-evidence-ledger.md", help="Output markdown file.")
    args = parser.parse_args()

    claims_path = Path(args.claims_file)
    claims = load_claims(claims_path)
    output = render_markdown(claims)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output, encoding="utf-8")
    print(str(out_path))


if __name__ == "__main__":
    main()
