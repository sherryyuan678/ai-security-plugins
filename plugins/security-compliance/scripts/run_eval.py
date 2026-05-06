#!/usr/bin/env python3
"""Programmatic evaluation runner for security-compliance-v2 suites."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from matching import (
    FRAMEWORK_ALIASES as DEFAULT_EXPECTED_FRAMEWORK_ALIASES,
    MUST_INCLUDE_ALIASES as DEFAULT_MUST_INCLUDE_ALIASES,
    EXCLUSION_CONTEXT_PATTERNS,
    _term_candidates,
    contains_all,
    contains_any,
    contains_forbidden_with_context,
    is_exclusion_context,
)


API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

COMPACT_EVAL_SYSTEM_PROMPT = """\
You are generating the final markdown report for a regulatory compliance assessment.

Output only final report content. Do not include setup narration, tool calls, XML tags,
function invocation markup, shell commands, checkpoint prompts, or file-write instructions.

## Scope discipline rules

- In the Regulatory Applicability Assessment, only discuss frameworks that ARE applicable
  to the described scenario.  State scope boundaries without naming excluded frameworks
  (e.g. write "No healthcare data obligations apply" instead of "HIPAA does not apply").
- Do NOT reference inapplicable frameworks by name anywhere in the report, including
  comparison tables, future-consideration sections, or exclusion lists.
- If the scenario references a regulation you cannot verify as real or currently in force,
  flag it with REQUIRES VALIDATION and do NOT generate detailed requirements for it.
- If the scenario requests compliance guidance for a regulation that clearly does not
  apply to the described entity, state its inapplicability once in Section 1 and do not
  reference it again.

## Baseline framework guidance

- Include both mandatory regulatory requirements AND industry-standard attestation
  frameworks that are practically required for the business context, even if not legally
  mandated.
- SOC 2 Type II is baseline for any SaaS, cloud, or technology service provider serving
  external customers or processing their data.
- ISO 27001 is baseline for any organisation selling to enterprise customers.
- NIST CSF is a standard risk-management framework for US-based organisations.
- Do NOT recommend SOC 2 or ISO 27001 for purely internal tools with no external
  customers, data processing obligations, or regulatory triggers.

## Terminology

Use standard framework abbreviations consistently throughout the report:
SOC 2, ISO 27001, NIST CSF, CCPA/CPRA, DORA, EU AI Act, PCI DSS, HIPAA, FedRAMP, CMMC.

When discussing conflict resolution between frameworks, explicitly describe the
justification approach using phrases such as: risk-based justification, retention schedule,
legal hold, single implementation, duplicate effort, regulatory timeline harmonization.

## Section order

1. Regulatory Applicability Assessment
2. Compliance Gap Analysis
3. Cross-Framework Control Map
4. Prioritized Implementation Roadmap
5. Technical Control Implementations
6. Policy and Documentation Templates
7. Automated Compliance Pipeline
8. Audit Preparation Package
9. Emerging Compliance Considerations (only when include-emerging is explicitly requested)

Keep the response thorough but not verbose (target <= 1800 words).
If facts are uncertain, mark REQUIRES VALIDATION.
"""

# ---------------------------------------------------------------------------
# LLM-as-judge semantic scoring (Opus 4.6)
# ---------------------------------------------------------------------------

DEFAULT_JUDGE_MODEL = "claude-opus-4-6"

JUDGE_SYSTEM_PROMPT = """\
You are an expert security compliance evaluator performing quality assessment \
of an AI-generated regulatory compliance report.  You operate at Staff Security \
Engineer level for enterprise organisations.

You will receive:
1. The compliance scenario (arguments)
2. The AI-generated report
3. Specific evaluation dimensions with descriptions

Return ONLY a valid JSON object — no markdown code fences, no text outside the \
JSON.

Structure:
{
  "dimension_scores": {
    "<dimension>": {"score": <float 0.0-1.0>, "rationale": "<1-2 sentences>"}
  },
  "factual_issues": ["<specific factual errors, empty list if none>"],
  "hallucination_flags": ["<fabricated regulations, invented dates, or false claims, empty list if none>"],
  "overall_semantic_score": <float 0.0-1.0>,
  "overall_rationale": "<2-3 sentence quality summary>"
}

Scoring scale:
  1.0 = Excellent — fully correct, complete, enterprise-grade
  0.8 = Good — minor gaps, no material errors
  0.6 = Acceptable — some notable issues but directionally correct
  0.4 = Below expectations — significant errors or omissions
  0.2 = Poor — major factual errors or dangerous recommendations
  0.0 = Failing — fundamentally wrong or harmful

Be strict.  Enterprise compliance quality is the standard.
Hallucinated regulations or fabricated facts MUST score 0.0 on factual_correctness.
"""

DIMENSION_DESCRIPTIONS: Dict[str, str] = {
    "applicability_accuracy": (
        "Correctly identifies which frameworks apply based on jurisdiction, "
        "industry, and data types, and correctly excludes inapplicable frameworks."
    ),
    "factual_correctness": (
        "All regulatory citations, effective dates, thresholds, and requirements "
        "are factually accurate.  No hallucinated or invented information."
    ),
    "actionability": (
        "Provides specific, implementable guidance with concrete steps, timelines, "
        "and technical controls rather than generic advice."
    ),
    "control_deduplication": (
        "Identifies overlapping controls across frameworks and recommends "
        "consolidated implementations rather than duplicative work."
    ),
    "scope_discipline": (
        "Avoids recommending frameworks, regulations, or controls not relevant "
        "to the scenario.  Resists over-scoping."
    ),
    "efficiency": (
        "Prioritises recommendations by impact and effort.  Avoids unnecessary "
        "complexity."
    ),
    "adversarial_robustness": (
        "Correctly handles edge cases: flags unknown or unverifiable regulations, "
        "respects temporal boundaries (e.g. as-of dates), refuses to validate "
        "fabricated claims, and resists prompt-based over-scoping pressure."
    ),
}


def read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8") as f:
        return f.read()


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def iter_suite_files(suite: str | None, run_all: bool, suites_dir: Path) -> List[Path]:
    if run_all:
        return sorted(suites_dir.glob("*.jsonl"))
    if not suite:
        raise ValueError("Provide --suite or --all.")
    suite_path = Path(suite)
    if suite_path.exists():
        return [suite_path]
    fallback = suites_dir / suite
    if fallback.exists():
        return [fallback]
    raise FileNotFoundError(f"Suite not found: {suite}")


def build_system_prompt(command_text: str, prompt_style: str) -> str:
    if prompt_style == "command":
        return (
            "You are executing a Claude Code plugin command specification. "
            "Follow the command exactly and produce the final report output.\n\n"
            + command_text
        )
    return COMPACT_EVAL_SYSTEM_PROMPT


RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 529}
MAX_RETRIES = 3


def call_anthropic(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
) -> str:
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    data = json.dumps(payload).encode("utf-8")

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(
            API_URL,
            data=data,
            headers={
                "content-type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            blocks = body.get("content", [])
            texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
            return "\n".join(texts).strip()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"API error {e.code}: {detail}")
            if e.code not in RETRYABLE_STATUS_CODES:
                raise last_error from e
            wait = 2 ** attempt  # 1s, 2s, 4s
            print(
                f"  [retry {attempt + 1}/{MAX_RETRIES}] {e.code} for model={model}, "
                f"waiting {wait}s ...",
                file=sys.stderr,
            )
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError) as e:
            last_error = RuntimeError(f"Network error: {e}")
            if attempt >= MAX_RETRIES:
                raise last_error from e
            wait = 2 ** attempt
            print(
                f"  [retry {attempt + 1}/{MAX_RETRIES}] network error, "
                f"waiting {wait}s ...",
                file=sys.stderr,
            )
            time.sleep(wait)

    raise last_error or RuntimeError("call_anthropic: all retries exhausted")


def judge_response(
    api_key: str,
    judge_model: str,
    case: Dict[str, Any],
    response: str,
    dimensions: List[str],
    max_tokens: int = 1500,
) -> Dict[str, Any]:
    """Call an LLM judge to semantically evaluate a compliance report."""
    dim_lines = "\n".join(
        f"- **{d}**: {DIMENSION_DESCRIPTIONS.get(d, 'Evaluate quality on this dimension.')}"
        for d in dimensions
    )

    adversarial_ctx = ""
    adversarial_hints = case.get("adversarial_hints", [])
    if adversarial_hints:
        hint_lines = "\n".join(f"- {h}" for h in adversarial_hints)
        adversarial_ctx = (
            "\n\n## Adversarial Evaluation Notes\n"
            "This is an adversarial test case.  Watch specifically for:\n"
            f"{hint_lines}"
        )

    user_prompt = (
        f"## Compliance Scenario\n\n{case.get('arguments', '')}\n\n"
        f"## AI-Generated Report\n\n{response}\n\n"
        f"## Dimensions to Evaluate\n\n{dim_lines}"
        f"{adversarial_ctx}\n\n"
        "Return only valid JSON matching the specified structure."
    )

    raw = call_anthropic(
        api_key=api_key,
        model=judge_model,
        system_prompt=JUDGE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_tokens=max_tokens,
    )

    try:
        cleaned = raw.strip()
        # Strip markdown code fences if present
        if cleaned.startswith("```"):
            first_nl = cleaned.index("\n")
            cleaned = cleaned[first_nl + 1 :]
            if "```" in cleaned:
                cleaned = cleaned[: cleaned.rindex("```")]
        return json.loads(cleaned.strip())
    except (json.JSONDecodeError, ValueError) as exc:
        print(
            f"  [judge] parse error for case {case.get('id', '?')}: {exc}\n"
            f"  [judge] raw response (first 300 chars): {raw[:300]}",
            file=sys.stderr,
        )
        return {
            "parse_error": True,
            "raw_response": raw[:500],
            "dimension_scores": {},
            "factual_issues": [],
            "hallucination_flags": [],
            "overall_semantic_score": 0.0,
            "overall_rationale": "Judge response could not be parsed as JSON.",
        }


def score_case(
    case: Dict[str, Any],
    response: str,
    strict: bool,
    must_include_aliases: Dict[str, List[str]] | None = None,
) -> Dict[str, Any]:
    expected = case.get("expected_frameworks", [])
    forbidden = case.get("forbidden_frameworks", [])
    must_include = case.get("must_include", [])
    must_not_include = case.get("must_not_include", [])

    exp_found, exp_missing = contains_all(
        response,
        expected,
        alias_map=DEFAULT_EXPECTED_FRAMEWORK_ALIASES,
    )
    include_found, include_missing = contains_all(
        response,
        must_include,
        alias_map=must_include_aliases,
    )
    forbidden_hits, forbidden_context_ignored = contains_forbidden_with_context(response, forbidden)
    must_not_hits = contains_any(response, must_not_include)

    total_assertions = (
        len(expected) + len(forbidden) + len(must_include) + len(must_not_include)
    )
    passed_assertions = (
        len(exp_found)
        + (len(forbidden) - len(forbidden_hits))
        + len(include_found)
        + (len(must_not_include) - len(must_not_hits))
    )
    score = round((passed_assertions / total_assertions), 4) if total_assertions else 1.0

    hard_fail = strict and (len(forbidden_hits) > 0 or len(must_not_hits) > 0)
    status = "pass" if (score == 1.0 and not hard_fail) else "fail"

    expected_score = (len(exp_found) / len(expected)) if expected else 1.0
    forbidden_score = ((len(forbidden) - len(forbidden_hits)) / len(forbidden)) if forbidden else 1.0
    must_include_score = (len(include_found) / len(must_include)) if must_include else 1.0
    must_not_score = (
        (len(must_not_include) - len(must_not_hits)) / len(must_not_include)
    ) if must_not_include else 1.0

    return {
        "status": status,
        "score": score,
        "total_assertions": total_assertions,
        "passed_assertions": passed_assertions,
        "expected_found": exp_found,
        "expected_missing": exp_missing,
        "must_include_missing": include_missing,
        "forbidden_hits": forbidden_hits,
        "forbidden_context_ignored": forbidden_context_ignored,
        "must_not_hits": must_not_hits,
        "assertion_component_scores": {
            "expected_frameworks": round(expected_score, 4),
            "forbidden_frameworks": round(forbidden_score, 4),
            "must_include": round(must_include_score, 4),
            "must_not_include": round(must_not_score, 4),
        },
        "hard_fail": hard_fail,
    }


def write_summary(results: List[Dict[str, Any]], out_dir: Path) -> None:
    total = len(results)
    passed = sum(1 for r in results if r["evaluation"]["status"] == "pass")
    failed = total - passed
    avg_score = round(sum(r["evaluation"]["score"] for r in results) / total, 4) if total else 0.0

    by_suite: Dict[str, Dict[str, int]] = {}
    for row in results:
        suite = row["suite"]
        by_suite.setdefault(suite, {"total": 0, "passed": 0, "failed": 0})
        by_suite[suite]["total"] += 1
        if row["evaluation"]["status"] == "pass":
            by_suite[suite]["passed"] += 1
        else:
            by_suite[suite]["failed"] += 1

    lines: List[str] = []
    lines.append("# Evaluation Summary")
    lines.append("")
    lines.append(f"- Total cases: {total}")
    lines.append(f"- Passed: {passed}")
    lines.append(f"- Failed: {failed}")
    lines.append(f"- Average score: {avg_score}")
    lines.append("")
    lines.append("## Per-suite")
    lines.append("")
    lines.append("| Suite | Total | Passed | Failed | Pass Rate |")
    lines.append("|---|---:|---:|---:|---:|")
    for suite, stats in sorted(by_suite.items()):
        rate = (stats["passed"] / stats["total"]) if stats["total"] else 0
        lines.append(
            f"| {suite} | {stats['total']} | {stats['passed']} | {stats['failed']} | {rate:.2%} |"
        )

    summary_path = out_dir / "summary.md"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    default_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Run security-compliance-v2 evaluation suites.")
    parser.add_argument("--suite", help="Path/name of a single suite JSONL file.")
    parser.add_argument("--all", action="store_true", help="Run all suites in tests/suites.")
    parser.add_argument("--root", default=str(default_root), help="Plugin/package root directory.")
    parser.add_argument("--out", default="tests/results", help="Output directory root.")
    parser.add_argument("--model", default=os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL))
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--strict", action="store_true", help="Enable hard-fail assertions.")
    parser.add_argument("--dry-run", action="store_true", help="Skip API calls.")
    parser.add_argument(
        "--prompt-style",
        choices=["compact", "command"],
        default="compact",
        help="Prompt style for model instructions; compact reduces truncation/tool-call spillover.",
    )
    parser.add_argument(
        "--command-file",
        default="commands/compliance-check.md",
        help="Command file used as instruction template."
    )
    parser.add_argument(
        "--suites-dir",
        default="tests/suites",
        help="Directory containing suite JSONL files."
    )
    parser.add_argument(
        "--enable-judge",
        action="store_true",
        help="Enable LLM-as-judge semantic scoring (requires API key; uses Opus 4.6 by default).",
    )
    parser.add_argument(
        "--judge-model",
        default=os.getenv("JUDGE_MODEL", DEFAULT_JUDGE_MODEL),
        help="Model to use for LLM judge evaluation.",
    )
    parser.add_argument(
        "--judge-max-tokens",
        type=int,
        default=1500,
        help="Max tokens for judge response.",
    )
    parser.add_argument(
        "--resume",
        default="",
        help="Resume a previous run.  Pass the timestamped output directory "
             "(e.g. tests/results/20260215T094656Z).  Existing response files "
             "are reused; only missing cases hit the API.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    suites_dir = root / args.suites_dir
    suite_files = iter_suite_files(args.suite, args.all, suites_dir)

    if not args.dry_run:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("ERROR: ANTHROPIC_API_KEY is required unless --dry-run is used.", file=sys.stderr)
            sys.exit(2)
    else:
        api_key = ""

    command_text = read_text(root / args.command_file) if args.prompt_style == "command" else ""
    system_prompt = build_system_prompt(command_text=command_text, prompt_style=args.prompt_style)

    # --- Output directory: new or resumed ----------------------------------
    if args.resume:
        resume_path = Path(args.resume)
        if not resume_path.is_absolute():
            resume_path = root / resume_path
        if not resume_path.is_dir():
            print(f"ERROR: resume directory not found: {resume_path}", file=sys.stderr)
            sys.exit(2)
        out_dir = resume_path
    else:
        run_ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = root / args.out / run_ts
    responses_dir = out_dir / "responses"
    responses_dir.mkdir(parents=True, exist_ok=True)

    # --- Save run config manifest ------------------------------------------
    run_config: Dict[str, Any] = {
        "started_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "model": args.model,
        "prompt_style": args.prompt_style,
        "strict": args.strict,
        "max_tokens": args.max_tokens,
        "enable_judge": args.enable_judge,
        "judge_model": args.judge_model if args.enable_judge else None,
        "judge_max_tokens": args.judge_max_tokens if args.enable_judge else None,
        "suites": [p.name for p in suite_files],
        "resumed_from": args.resume or None,
        "dry_run": args.dry_run,
    }
    config_path = out_dir / "run_config.json"
    config_path.write_text(json.dumps(run_config, indent=2) + "\n", encoding="utf-8")

    # --- Load checkpoint: completed results from a previous partial run ----
    results_path = out_dir / "results.jsonl"
    completed: Dict[str, Dict[str, Any]] = {}
    if args.resume:
        # Load from results.jsonl first (clean, deduplicated)
        if results_path.exists():
            for row in load_jsonl(results_path):
                cid = row.get("case_id", "")
                if cid:
                    completed[cid] = row
        # Also load from _checkpoint.jsonl (crash-recovery; may have entries
        # not yet in results.jsonl).  Later entries for the same case_id win.
        checkpoint_recovery = out_dir / "_checkpoint.jsonl"
        if checkpoint_recovery.exists():
            for row in load_jsonl(checkpoint_recovery):
                cid = row.get("case_id", "")
                if cid and cid not in completed:
                    completed[cid] = row
        if completed:
            print(
                f"  [resume] loaded {len(completed)} completed results from checkpoint",
                file=sys.stderr,
            )

    # --- Incremental checkpoint file (append as each case finishes) --------
    checkpoint_path = out_dir / "_checkpoint.jsonl"
    checkpoint_fh = checkpoint_path.open("a", encoding="utf-8")

    all_results: List[Dict[str, Any]] = []

    for suite_path in suite_files:
        cases = load_jsonl(suite_path)
        suite_name = suite_path.name
        for idx, case in enumerate(cases, start=1):
            case_id = case.get("id", f"{suite_name}-{idx:03d}")
            arguments = case.get("arguments", "")

            # --- Check if fully completed in a previous run ----------------
            existing = completed.get(case_id)
            if existing:
                has_judge = "judge" in existing
                judge_needed = args.enable_judge and not args.dry_run
                if has_judge or not judge_needed:
                    all_results.append(existing)
                    print(f"  [resume] complete: {case_id}", file=sys.stderr)
                    continue
                # Has response+score but missing judge -- fall through to
                # reuse response and add judge below.

            # --- Get response: from disk, dry-run, or API ------------------
            response_path = responses_dir / f"{case_id}.md"

            if response_path.exists():
                response = response_path.read_text(encoding="utf-8").rstrip("\n")
                print(f"  [resume] reusing response: {case_id}", file=sys.stderr)
            elif args.dry_run:
                response = (
                    "DRY RUN: no API call executed.\n\n"
                    f"Case: {case_id}\nArguments: {arguments}"
                )
                response_path.write_text(response + "\n", encoding="utf-8")
            else:
                user_prompt = (
                    "Generate the final compliance report for this scenario.\n\n"
                    "Arguments:\n"
                    f"{arguments}\n\n"
                    "Return markdown final report sections only. "
                    "Do not include function calls, XML tags, setup narration, or checkpoint prompts."
                )
                response = call_anthropic(
                    api_key=api_key,
                    model=args.model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=args.max_tokens,
                )
                response_path.write_text(response + "\n", encoding="utf-8")

            # --- Assertion scoring -----------------------------------------
            evaluation = score_case(
                case,
                response,
                strict=args.strict,
                must_include_aliases=DEFAULT_MUST_INCLUDE_ALIASES,
            )

            # --- LLM-as-judge semantic evaluation (optional) ---------------
            judge_result: Dict[str, Any] | None = None
            if args.enable_judge and not args.dry_run:
                dims = case.get("dimensions", [])
                if dims:
                    judge_result = judge_response(
                        api_key=api_key,
                        judge_model=args.judge_model,
                        case=case,
                        response=response,
                        dimensions=dims,
                        max_tokens=args.judge_max_tokens,
                    )

            row: Dict[str, Any] = {
                "timestamp_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "suite": suite_name,
                "case_id": case_id,
                "arguments": arguments,
                "dimensions": case.get("dimensions", []),
                "model": args.model,
                "prompt_style": args.prompt_style,
                "response_file": str(response_path.relative_to(out_dir)),
                "evaluation": evaluation,
            }
            if judge_result is not None:
                row["judge"] = {
                    "model": args.judge_model,
                    **judge_result,
                }

            # --- Incremental checkpoint (crash-safe) -----------------------
            checkpoint_fh.write(json.dumps(row, ensure_ascii=True) + "\n")
            checkpoint_fh.flush()

            all_results.append(row)

    checkpoint_fh.close()

    # --- Write final artifacts (clean, ordered) ----------------------------
    with results_path.open("w", encoding="utf-8") as f:
        for row in all_results:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")

    write_summary(all_results, out_dir)

    # Clean up checkpoint file on successful completion
    if checkpoint_path.exists():
        checkpoint_path.unlink()

    # Mark run as finished
    run_config["finished_utc"] = (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    run_config["total_cases"] = len(all_results)
    run_config["passed"] = sum(
        1 for r in all_results if r.get("evaluation", {}).get("status") == "pass"
    )
    config_path.write_text(json.dumps(run_config, indent=2) + "\n", encoding="utf-8")

    print(str(out_dir))


if __name__ == "__main__":
    main()
