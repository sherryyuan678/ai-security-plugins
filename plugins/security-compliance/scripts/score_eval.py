#!/usr/bin/env python3
"""Aggregate eval results with rubric weights, blending assertion and LLM-judge scores."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


SUITE_DIMENSION_FALLBACK: Dict[str, List[str]] = {
    "suite_01_jurisdictional_applicability.jsonl": ["applicability_accuracy", "scope_discipline"],
    "suite_02_dora_depth.jsonl": ["factual_correctness", "actionability"],
    "suite_03_eu_ai_act_classification.jsonl": ["applicability_accuracy", "factual_correctness"],
    "suite_04_control_consolidation.jsonl": ["control_deduplication", "actionability"],
    "suite_05_scope_discipline.jsonl": ["scope_discipline", "efficiency"],
    "suite_06_iso_nist_baseline_coverage.jsonl": ["applicability_accuracy", "control_deduplication"],
    "suite_07_cross_border_transfer_controls.jsonl": ["factual_correctness", "actionability"],
    "suite_08_framework_conflict_resolution.jsonl": ["control_deduplication", "factual_correctness"],
    "suite_09_adversarial_robustness.jsonl": ["adversarial_robustness", "factual_correctness"],
}

DEFAULT_BLEND_WEIGHT = 0.50  # 0.0 = assertion-only, 1.0 = judge-only


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def wilson_interval(successes: int, total: int, z: float = 1.96) -> Dict[str, float]:
    if total == 0:
        return {"low": 0.0, "high": 0.0}
    p = successes / total
    denom = 1 + (z * z) / total
    center = (p + (z * z) / (2 * total)) / denom
    margin = (z / denom) * math.sqrt((p * (1 - p) / total) + ((z * z) / (4 * total * total)))
    return {
        "low": round(max(0.0, center - margin), 4),
        "high": round(min(1.0, center + margin), 4),
    }


def normalized_dimensions(row: Dict[str, Any]) -> List[str]:
    dims = row.get("dimensions")
    if isinstance(dims, list) and dims:
        return [str(d).strip() for d in dims if str(d).strip()]

    suite = str(row.get("suite", ""))
    return SUITE_DIMENSION_FALLBACK.get(suite, [])


def _judge_dim_score(row: Dict[str, Any], dim: str) -> Optional[float]:
    """Extract a single dimension score from judge data, if present and valid."""
    judge = row.get("judge")
    if not judge or judge.get("parse_error"):
        return None
    dim_scores = judge.get("dimension_scores", {})
    entry = dim_scores.get(dim)
    if isinstance(entry, dict) and "score" in entry:
        return float(entry["score"])
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Score eval run output with rubric metadata.")
    parser.add_argument("--results", required=True, help="Path to results.jsonl")
    parser.add_argument("--rubric", default="tests/rubric/scoring_rubric.json")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    results = load_jsonl(Path(args.results))
    rubric = json.loads(Path(args.rubric).read_text(encoding="utf-8"))

    dimensions_cfg: Dict[str, float] = rubric.get("dimensions", {})
    thresholds = rubric.get("thresholds", {})
    blend_weight = float(rubric.get("judge", {}).get("blend_weight", DEFAULT_BLEND_WEIGHT))

    # ---- Global aggregates ------------------------------------------------
    total = len(results)
    avg_score = sum(r["evaluation"]["score"] for r in results) / total if total else 0.0
    pass_count = sum(1 for r in results if r["evaluation"]["status"] == "pass")
    pass_rate = pass_count / total if total else 0.0
    pass_rate_ci95 = wilson_interval(pass_count, total)

    # ---- Per-suite stats --------------------------------------------------
    suite_totals: Dict[str, int] = {}
    suite_passes: Dict[str, int] = {}
    for row in results:
        suite = str(row.get("suite", "unknown"))
        suite_totals[suite] = suite_totals.get(suite, 0) + 1
        if row.get("evaluation", {}).get("status") == "pass":
            suite_passes[suite] = suite_passes.get(suite, 0) + 1

    suite_stats: Dict[str, Any] = {}
    for suite, count in sorted(suite_totals.items()):
        passed = suite_passes.get(suite, 0)
        rate = (passed / count) if count else 0.0
        suite_stats[suite] = {
            "cases": count,
            "pass_count": passed,
            "pass_rate": round(rate, 4),
            "pass_rate_ci95": wilson_interval(passed, count),
        }

    # ---- Per-dimension scoring (assertion + judge blend) ------------------
    assertion_dim_scores: Dict[str, List[float]] = {k: [] for k in dimensions_cfg}
    judge_dim_scores: Dict[str, List[float]] = {k: [] for k in dimensions_cfg}
    blended_dim_scores: Dict[str, List[float]] = {k: [] for k in dimensions_cfg}
    unknown_dimensions: Dict[str, int] = {}
    judge_case_count = 0

    for row in results:
        assertion_score = float(row.get("evaluation", {}).get("score", 0.0))
        has_judge = bool(
            row.get("judge")
            and not row["judge"].get("parse_error")
            and row["judge"].get("dimension_scores")
        )
        if has_judge:
            judge_case_count += 1

        dims = normalized_dimensions(row)
        for d in dims:
            if d not in assertion_dim_scores:
                unknown_dimensions[d] = unknown_dimensions.get(d, 0) + 1
                continue

            assertion_dim_scores[d].append(assertion_score)

            j_score = _judge_dim_score(row, d) if has_judge else None
            if j_score is not None:
                judge_dim_scores[d].append(j_score)
                blended = (1 - blend_weight) * assertion_score + blend_weight * j_score
            else:
                if blend_weight > 0 and has_judge:
                    print(
                        f"  [warn] case {row.get('case_id', '?')} dim={d}: "
                        f"judge data missing; using assertion score as fallback",
                        file=sys.stderr,
                    )
                blended = assertion_score
            blended_dim_scores[d].append(blended)

    min_dim_cases = int(thresholds.get("minimum_dimension_coverage_cases", 0))
    min_dim_score = float(thresholds.get("minimum_dimension_score", 0.0))

    per_dimension: Dict[str, Any] = {}
    weighted_assertion_score = 0.0
    weighted_blended_score = 0.0

    for dim, weight in dimensions_cfg.items():
        a_scores = assertion_dim_scores.get(dim, [])
        j_scores = judge_dim_scores.get(dim, [])
        b_scores = blended_dim_scores.get(dim, [])

        a_avg = (sum(a_scores) / len(a_scores)) if a_scores else 0.0
        j_avg = (sum(j_scores) / len(j_scores)) if j_scores else None
        b_avg = (sum(b_scores) / len(b_scores)) if b_scores else 0.0

        required_cases = max(1, min_dim_cases)
        meets_cases = len(a_scores) >= required_cases
        # Gate on blended average when judge data exists, else assertion-only
        effective_avg = b_avg
        meets_score = effective_avg >= min_dim_score

        entry: Dict[str, Any] = {
            "weight": weight,
            "case_count": len(a_scores),
            "assertion_average": round(a_avg, 4),
            "blended_average": round(b_avg, 4),
            "meets_min_cases": meets_cases,
            "meets_min_score": meets_score,
            "weighted_contribution": round(weight * b_avg, 4),
        }
        if j_avg is not None:
            entry["judge_average"] = round(j_avg, 4)
            entry["judge_case_count"] = len(j_scores)

        per_dimension[dim] = entry
        weighted_assertion_score += weight * a_avg
        weighted_blended_score += weight * b_avg

    # ---- Judge summary (when judge data is present) -----------------------
    judge_semantic_scores: List[float] = []
    total_hallucination_flags = 0
    total_factual_issues = 0
    adversarial_hallucination_flags = 0

    for row in results:
        judge_data = row.get("judge")
        if not judge_data or judge_data.get("parse_error"):
            continue
        sem = float(judge_data.get("overall_semantic_score", 0.0))
        judge_semantic_scores.append(sem)
        h_flags = judge_data.get("hallucination_flags", [])
        total_hallucination_flags += len(h_flags)
        total_factual_issues += len(judge_data.get("factual_issues", []))

        # Track hallucination flags specifically in the adversarial suite
        suite_name = str(row.get("suite", ""))
        if "adversarial" in suite_name and h_flags:
            adversarial_hallucination_flags += len(h_flags)

    judge_summary: Optional[Dict[str, Any]] = None
    if judge_semantic_scores:
        avg_sem = sum(judge_semantic_scores) / len(judge_semantic_scores)
        judge_summary = {
            "cases_judged": len(judge_semantic_scores),
            "avg_semantic_score": round(avg_sem, 4),
            "avg_semantic_score_ci95": wilson_interval(
                int(avg_sem * len(judge_semantic_scores)),
                len(judge_semantic_scores),
            ),
            "total_hallucination_flags": total_hallucination_flags,
            "adversarial_hallucination_flags": adversarial_hallucination_flags,
            "total_factual_issues": total_factual_issues,
        }

    # ---- Threshold checks -------------------------------------------------
    minimum_pass_rate = float(thresholds.get("minimum_pass_rate", 0.0))
    minimum_avg_assertion_score = float(thresholds.get("minimum_avg_assertion_score", 0.0))
    minimum_weighted_dimension_score = float(thresholds.get("minimum_weighted_dimension_score", 0.0))
    minimum_total_cases = int(thresholds.get("minimum_total_cases", 0))
    minimum_cases_per_suite = int(thresholds.get("minimum_cases_per_suite", 0))
    minimum_judge_semantic_score = float(thresholds.get("minimum_judge_semantic_score", 0.0))

    meets_min_cases_per_suite = True
    if minimum_cases_per_suite > 0 and suite_totals:
        meets_min_cases_per_suite = all(v >= minimum_cases_per_suite for v in suite_totals.values())

    meets_dimension_cases = all(v["meets_min_cases"] for v in per_dimension.values()) if per_dimension else True
    meets_dimension_scores = all(v["meets_min_score"] for v in per_dimension.values()) if per_dimension else True

    # Use blended weighted score when judge data is available
    effective_weighted = weighted_blended_score if judge_case_count > 0 else weighted_assertion_score

    meets_thresholds: Dict[str, bool] = {
        "minimum_pass_rate": pass_rate >= minimum_pass_rate,
        "minimum_avg_assertion_score": avg_score >= minimum_avg_assertion_score,
        "minimum_weighted_dimension_score": effective_weighted >= minimum_weighted_dimension_score,
        "minimum_total_cases": total >= minimum_total_cases,
        "minimum_cases_per_suite": meets_min_cases_per_suite,
        "minimum_dimension_coverage_cases": meets_dimension_cases,
        "minimum_dimension_score": meets_dimension_scores,
    }

    # Judge-specific gates (only enforced when judge data exists)
    if judge_summary:
        avg_sem_score = judge_summary["avg_semantic_score"]
        meets_thresholds["minimum_judge_semantic_score"] = avg_sem_score >= minimum_judge_semantic_score
        meets_thresholds["zero_adversarial_hallucinations"] = adversarial_hallucination_flags == 0

    meets_decision_gate = all(meets_thresholds.values()) if meets_thresholds else True

    # ---- Output -----------------------------------------------------------
    output: Dict[str, Any] = {
        "total_cases": total,
        "pass_count": pass_count,
        "pass_rate": round(pass_rate, 4),
        "pass_rate_ci95": pass_rate_ci95,
        "average_assertion_score": round(avg_score, 4),
        "weighted_assertion_score": round(weighted_assertion_score, 4),
        "weighted_blended_score": round(weighted_blended_score, 4),
        "blend_weight": blend_weight,
        "judge_enabled": judge_case_count > 0,
        "judge_case_count": judge_case_count,
        "suite_stats": suite_stats,
        "dimension_stats": per_dimension,
        "unknown_dimensions": unknown_dimensions,
    }
    if judge_summary:
        output["judge_summary"] = judge_summary
    output["rubric"] = rubric
    output["decision_rule"] = rubric.get("decision_rule", {})
    output["meets_thresholds"] = meets_thresholds
    output["meets_decision_gate"] = meets_decision_gate

    text = json.dumps(output, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
        print(str(out_path))
    else:
        print(text)


if __name__ == "__main__":
    main()
