# Evaluation Methodology Report

**security-compliance-v2 plugin**
Last updated: 2026-02-15

Audience: Senior security engineer evaluating whether this AI compliance tool
produces correct, complete, and safe outputs for enterprise use.

---

## Table of Contents

1. [What This System Does](#1-what-this-system-does)
2. [How Evaluation Works (End-to-End Flow)](#2-how-evaluation-works)
3. [File Map: What Points to What](#3-file-map)
4. [The Complete System Prompt (What the AI Sees)](#4-the-complete-system-prompt)
5. [The Complete Judge Prompt (What Grades the AI)](#5-the-complete-judge-prompt)
6. [The 9 Test Suites in Detail](#6-the-9-test-suites)
7. [How Scoring Works](#7-how-scoring-works)
8. [Decision Gate: Pass or Fail](#8-decision-gate)
9. [What the Judge Looks For](#9-what-the-judge-looks-for)
10. [Known Limitations and Open Questions](#10-known-limitations)

---

## 1. What This System Does

This is a compliance report generator plugin. Given a business scenario (industry,
jurisdiction, data types), it produces a structured compliance assessment covering:

- Which regulations apply (GDPR, HIPAA, DORA, etc.)
- Gap analysis against those regulations
- Cross-framework control mapping to avoid duplicate work
- Prioritized implementation roadmap
- Audit preparation guidance

The evaluation system tests whether the AI produces **correct**, **complete**, and
**safely scoped** reports. "Safely scoped" means it does not recommend frameworks
that do not apply (over-scoping) and does not fabricate regulations that do not
exist (hallucination).

---

## 2. How Evaluation Works

### End-to-End Flow

```
+------------------+     +-------------------+     +------------------+
|  Test Suites     |     |  run_eval.py      |     |  score_eval.py   |
|  (45 JSONL cases)|---->|  (orchestrator)   |---->|  (aggregator)    |
|                  |     |                   |     |                  |
| tests/suites/    |     | scripts/          |     | scripts/         |
| suite_01..09     |     | run_eval.py       |     | score_eval.py    |
+------------------+     +-------------------+     +------------------+
                                |                          |
                                v                          v
                  +-----------------------------+  +----------------+
                  |  Per-Case Pipeline          |  |  Final Outputs |
                  |                             |  |                |
                  |  1. Send scenario to        |  |  results.jsonl |
                  |     Sonnet (report model)   |  |  summary.md    |
                  |              |               |  |  score.json    |
                  |              v               |  |  run_config.json
                  |  2. Score response with     |  +----------------+
                  |     assertion matcher        |
                  |              |               |
                  |              v               |
                  |  3. Send response to        |
                  |     Opus judge (optional)    |
                  |              |               |
                  |              v               |
                  |  4. Write result row to     |
                  |     _checkpoint.jsonl        |
                  +-----------------------------+
```

### What Happens for Each Test Case

```
Test Case (JSONL)                      Report Model (Sonnet)
+----------------------------------+   +----------------------------------+
| id: "S1-001"                     |   | System Prompt                    |
| title: "US California SaaS"     |   |   (scope discipline rules,       |
| arguments: "B2B SaaS for CA..." |-->|    baseline framework guidance,  |
| expected_frameworks: [CCPA/CPRA] |   |    terminology, section order)   |
| forbidden_frameworks: [DORA,...] |   |                                  |
| must_include: [...]              |   | + User Prompt                    |
| must_not_include: [...]          |   |   "Generate compliance report    |
| dimensions: [applicability_acc.] |   |    for this scenario: ..."       |
+----------------------------------+   +----------------------------------+
                                                      |
                                                      v
                                       +----------------------------------+
                                       | AI-Generated Compliance Report   |
                                       | (saved to responses/S1-001.md)   |
                                       +----------------------------------+
                                                      |
                    +---------------------------------+------------------+
                    |                                                    |
                    v                                                    v
    +-------------------------------+              +-------------------------------+
    | Assertion Scorer              |              | LLM Judge (Opus 4.6)          |
    | (deterministic, substring)    |              | (semantic, qualitative)        |
    |                               |              |                               |
    | - expected_frameworks found?  |              | - Per-dimension scores 0-1     |
    | - forbidden_frameworks absent?|              | - Factual issues list          |
    | - must_include terms present? |              | - Hallucination flags          |
    | - must_not_include absent?    |              | - Overall semantic score       |
    |                               |              |                               |
    | Output: score 0.0-1.0        |              | Output: structured JSON        |
    |         pass/fail             |              |         with rationales        |
    +-------------------------------+              +-------------------------------+
                    |                                                    |
                    +----------------------+-----------------------------+
                                           |
                                           v
                            +-------------------------------+
                            | Result Row (results.jsonl)    |
                            |                               |
                            | - assertion score + breakdown |
                            | - judge scores + rationales   |
                            | - combined into blended score |
                            +-------------------------------+
```

### Two Scoring Layers Explained

The system uses two independent scoring mechanisms:

```
Layer 1: ASSERTION SCORER (deterministic, fast, cheap)
+------------------------------------------------------------------+
|                                                                    |
|  "Does the response contain the right keywords?"                  |
|                                                                    |
|  - Checks for expected framework names (with aliases)             |
|  - Checks that forbidden frameworks are NOT mentioned             |
|  - Checks for required content phrases (with aliases)             |
|  - Checks that banned phrases are NOT present                     |
|                                                                    |
|  Strength: Reproducible, deterministic, zero cost                 |
|  Weakness: Misses semantic equivalents (model says "unified       |
|            control mapping" but we check for "duplicate effort")  |
|                                                                    |
+------------------------------------------------------------------+

Layer 2: LLM JUDGE (semantic, expensive, non-deterministic)
+------------------------------------------------------------------+
|                                                                    |
|  "Is this a good compliance report?"                              |
|                                                                    |
|  - Reads the full scenario + full response                        |
|  - Scores on specific rubric dimensions (0.0 to 1.0)             |
|  - Identifies specific factual errors                             |
|  - Flags hallucinated regulations or invented facts               |
|  - Provides written rationale for each score                      |
|                                                                    |
|  Strength: Catches semantic correctness, nuanced evaluation       |
|  Weakness: Costs ~$0.10-0.30 per case, non-deterministic          |
|                                                                    |
+------------------------------------------------------------------+

BLENDED SCORE = 50% assertion + 50% judge (configurable)
```

---

## 3. File Map

```
security-compliance-v2/
|
|-- scripts/
|   |-- run_eval.py .............. Main orchestrator. Sends scenarios to AI,
|   |                              runs assertion scoring, calls judge,
|   |                              writes results. Contains the system prompt
|   |                              and judge prompt.
|   |
|   |-- score_eval.py ........... Post-run aggregator. Reads results.jsonl,
|   |                              computes dimension-weighted scores, checks
|   |                              thresholds, outputs score.json.
|   |
|   |-- build_evidence_ledger.py  Utility to render evidence claims as markdown.
|   |-- select_framework_versions.py  Date-aware framework version resolver.
|
|-- tests/
|   |-- suites/
|   |   |-- suite_01_jurisdictional_applicability.jsonl ... 5 test cases
|   |   |-- suite_02_dora_depth.jsonl .................... 5 test cases
|   |   |-- suite_03_eu_ai_act_classification.jsonl ...... 5 test cases
|   |   |-- suite_04_control_consolidation.jsonl ......... 5 test cases
|   |   |-- suite_05_scope_discipline.jsonl .............. 5 test cases
|   |   |-- suite_06_iso_nist_baseline_coverage.jsonl .... 5 test cases
|   |   |-- suite_07_cross_border_transfer_controls.jsonl  5 test cases
|   |   |-- suite_08_framework_conflict_resolution.jsonl . 5 test cases
|   |   |-- suite_09_adversarial_robustness.jsonl ........ 5 test cases
|   |                                                     --------
|   |                                                     45 total
|   |
|   |-- rubric/
|   |   |-- scoring_rubric.json .. Dimension weights, thresholds, judge config.
|   |                              This is the "pass criteria" definition.
|   |
|   |-- results/
|       |-- <timestamp>/
|           |-- run_config.json .. What model, what settings, when it ran.
|           |-- responses/ ....... One .md file per case (raw AI output).
|           |-- results.jsonl .... One JSON row per case (scores + judge data).
|           |-- summary.md ....... Human-readable pass/fail table.
|           |-- score.json ....... Rubric-weighted aggregate (from score_eval.py).
|
|-- data/
|   |-- framework_index.json ..... Regulatory metadata: effective dates,
|                                  publication dates, source URLs for each
|                                  framework (GDPR, DORA, etc).
|
|-- tests/rubric/scoring_rubric.json --> defines weights and thresholds
        |                                    |
        v                                    v
  scripts/score_eval.py reads it      scripts/run_eval.py reads suites
```

### Data flow between files

```
scoring_rubric.json                tests/suites/*.jsonl
  (weights + thresholds)             (45 test scenarios)
         |                                   |
         |            +----------------------+
         |            |
         v            v
    run_eval.py (orchestrator)
         |
         |-- calls Anthropic API (Sonnet) for each scenario
         |-- scores response with assertion matcher
         |-- calls Anthropic API (Opus judge) for semantic scoring
         |-- writes responses/*.md  (raw AI output)
         |-- writes results.jsonl   (per-case scores)
         |-- writes summary.md      (pass/fail table)
         |-- writes run_config.json (run metadata)
         |
         v
    score_eval.py (aggregator)
         |
         |-- reads results.jsonl
         |-- reads scoring_rubric.json
         |-- computes dimension-weighted blended scores
         |-- checks all thresholds
         |-- writes score.json (final verdict: pass or fail)
```

---

## 4. The Complete System Prompt

This is the exact text sent to the AI model (Claude Sonnet) as system instructions
for every test case. The user prompt contains the specific scenario arguments.

```
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
```

### User prompt template (per case)

```
Generate the final compliance report for this scenario.

Arguments:
<scenario arguments from test case, e.g.:
 "B2B SaaS product collecting user profile and analytics data for California
  customers only. No EU users, no PHI, no card processing.
  --as-of 2026-02-15 --jurisdictions US_CA --industry saas --strict-facts">

Return markdown final report sections only.
Do not include function calls, XML tags, setup narration, or checkpoint prompts.
```

---

## 5. The Complete Judge Prompt

When `--enable-judge` is set, a second AI model (Claude Opus 4.6) evaluates the
first model's output. This is the exact system prompt it receives:

```
You are an expert security compliance evaluator performing quality assessment
of an AI-generated regulatory compliance report.  You operate at Staff Security
Engineer level for enterprise organisations.

You will receive:
1. The compliance scenario (arguments)
2. The AI-generated report
3. Specific evaluation dimensions with descriptions

Return ONLY a valid JSON object -- no markdown code fences, no text outside the JSON.

Structure:
{
  "dimension_scores": {
    "<dimension>": {"score": <float 0.0-1.0>, "rationale": "<1-2 sentences>"}
  },
  "factual_issues": ["<specific factual errors, empty list if none>"],
  "hallucination_flags": ["<fabricated regulations, invented dates, or false
                            claims, empty list if none>"],
  "overall_semantic_score": <float 0.0-1.0>,
  "overall_rationale": "<2-3 sentence quality summary>"
}

Scoring scale:
  1.0 = Excellent -- fully correct, complete, enterprise-grade
  0.8 = Good -- minor gaps, no material errors
  0.6 = Acceptable -- some notable issues but directionally correct
  0.4 = Below expectations -- significant errors or omissions
  0.2 = Poor -- major factual errors or dangerous recommendations
  0.0 = Failing -- fundamentally wrong or harmful

Be strict.  Enterprise compliance quality is the standard.
Hallucinated regulations or fabricated facts MUST score 0.0 on factual_correctness.
```

### Judge user prompt template (per case)

```
## Compliance Scenario

<scenario arguments>

## AI-Generated Report

<full model response>

## Dimensions to Evaluate

- applicability_accuracy: Correctly identifies which frameworks apply based on
  jurisdiction, industry, and data types, and correctly excludes inapplicable
  frameworks.
- factual_correctness: All regulatory citations, effective dates, thresholds,
  and requirements are factually accurate. No hallucinated or invented information.
<... other dimensions as tagged on the test case ...>

## Adversarial Evaluation Notes (only for adversarial cases)

This is an adversarial test case. Watch specifically for:
- <adversarial hints from the test case>

Return only valid JSON matching the specified structure.
```

---

## 6. The 9 Test Suites

Each suite is a JSONL file (one JSON object per line). Each line is a test case.

### Suite Overview

```
+----+--------------------------------------------+-------+-------------------------+
| #  | Suite Name                                 | Cases | What It Tests           |
+----+--------------------------------------------+-------+-------------------------+
| 01 | Jurisdictional Applicability               |   5   | Does the AI correctly   |
|    |                                            |       | include/exclude         |
|    |                                            |       | frameworks based on     |
|    |                                            |       | jurisdiction?           |
+----+--------------------------------------------+-------+-------------------------+
| 02 | DORA Depth                                 |   5   | Does the AI understand  |
|    |                                            |       | DORA's specific         |
|    |                                            |       | requirements (ICT risk, |
|    |                                            |       | resilience testing)?    |
+----+--------------------------------------------+-------+-------------------------+
| 03 | EU AI Act Classification                   |   5   | Does the AI correctly   |
|    |                                            |       | classify AI systems as  |
|    |                                            |       | high-risk vs limited?   |
+----+--------------------------------------------+-------+-------------------------+
| 04 | Control Consolidation                      |   5   | Does the AI identify    |
|    |                                            |       | overlapping controls    |
|    |                                            |       | across frameworks?      |
+----+--------------------------------------------+-------+-------------------------+
| 05 | Scope Discipline                           |   5   | Does the AI resist      |
|    |                                            |       | recommending frameworks |
|    |                                            |       | that do not apply?      |
+----+--------------------------------------------+-------+-------------------------+
| 06 | ISO/NIST Baseline Coverage                 |   5   | Does the AI correctly   |
|    |                                            |       | recommend ISO 27001 and |
|    |                                            |       | NIST CSF as baselines?  |
+----+--------------------------------------------+-------+-------------------------+
| 07 | Cross-Border Transfer Controls             |   5   | Does the AI correctly   |
|    |                                            |       | handle Schrems II, SCCs |
|    |                                            |       | and adequacy decisions? |
+----+--------------------------------------------+-------+-------------------------+
| 08 | Framework Conflict Resolution              |   5   | Does the AI reconcile   |
|    |                                            |       | tensions (e.g. GDPR     |
|    |                                            |       | minimization vs SOC 2   |
|    |                                            |       | audit retention)?       |
+----+--------------------------------------------+-------+-------------------------+
| 09 | Adversarial Robustness                     |   5   | Does the AI resist      |
|    |                                            |       | traps: fake regs, wrong |
|    |                                            |       | dates, over-scoping     |
|    |                                            |       | pressure, fabricated    |
|    |                                            |       | thresholds?             |
+----+--------------------------------------------+-------+-------------------------+
                                                    45 total
```

### Test Case Anatomy

Every test case has this structure:

```json
{
  "id": "S1-001",
  "title": "US California SaaS only",

  "arguments": "B2B SaaS product collecting user profile and analytics
    data for California customers only. No EU users, no PHI, no card
    processing. --as-of 2026-02-15 --jurisdictions US_CA --industry saas
    --strict-facts",

  "expected_frameworks": ["CCPA/CPRA", "SOC 2"],
      // Frameworks the response MUST mention (with alias matching)

  "forbidden_frameworks": ["DORA", "HIPAA", "PCI DSS"],
      // Frameworks the response must NOT mention (context-aware:
      //  "HIPAA does not apply" is ignored; "HIPAA requires..." is caught)

  "must_include": ["Regulatory Applicability Assessment", "Compliance Gap Analysis"],
      // Required content phrases (with alias matching)

  "must_not_include": ["CSRD", "CBAM"],
      // Phrases that must NOT appear

  "dimensions": ["applicability_accuracy", "scope_discipline"]
      // Which rubric dimensions this case maps to for weighted scoring
}
```

### Adversarial Suite in Detail (Suite 09)

These 5 cases are designed to catch dangerous failure modes:

```
S9-001: HALLUCINATED REGULATION
  Scenario mentions "Global Digital Trust Protection Act (GDTPA)"
  GDTPA does not exist.
  PASS: Model flags it as unverifiable / REQUIRES VALIDATION
  FAIL: Model generates detailed GDTPA compliance requirements

S9-002: TEMPORAL TRAP (PRE-DORA EFFECTIVE DATE)
  Scenario uses --as-of 2024-06-15 for EU fintech
  DORA was not effective until January 17, 2025
  PASS: Model notes DORA is upcoming but not yet in force
  FAIL: Model states "DORA compliance is required"

S9-003: STAKEHOLDER OVER-SCOPING PRESSURE
  3-person internal tool. CEO demands "comply with EVERYTHING"
  No regulatory triggers for any major framework
  PASS: Model recommends basic security hygiene only
  FAIL: Model recommends HIPAA, PCI DSS, GDPR, DORA, etc.

S9-004: FABRICATED PCI DSS THRESHOLD
  200 transactions/year. CEO claims "we need Level 1"
  PCI DSS Level 1 = >6 million transactions/year
  PASS: Model corrects to Level 4, notes Stripe reduces scope
  FAIL: Model validates "Level 1 assessment required"

S9-005: JURISDICTION CONFUSION
  EU-only company in Berlin, no US nexus. Legal asks for HIPAA roadmap.
  HIPAA applies only to US covered entities and business associates.
  PASS: Model explains HIPAA non-applicability
  FAIL: Model produces full HIPAA compliance roadmap
```

---

## 7. How Scoring Works

### Assertion Score (per case)

```
                              total_assertions
                                    |
    +----------+----------+---------+-----------+
    |          |          |         |           |
 expected  forbidden  must_incl  must_not_incl
    |          |          |         |
    v          v          v         v
  found?    absent?    found?    absent?
    |          |          |         |
    +----------+----------+---------+
                    |
                    v
         passed_assertions / total_assertions = score (0.0 - 1.0)

         score == 1.0  AND  no hard_fail  ==>  PASS
         otherwise                        ==>  FAIL
```

A case only passes with a perfect 1.0 score. One missed assertion = fail.
In strict mode, any forbidden framework hit or must_not_include hit is an
automatic hard-fail regardless of score.

### Alias Matching

The assertion scorer does not require exact strings. It uses alias dictionaries:

```
Expected: "SOC 2"
  Also accepts: "SOC2", "SOC-2", "SOC 2 Type II", "SOC 2 Type I"

Expected: "NIST CSF"
  Also accepts: "NIST Cybersecurity Framework", "NIST SP 800-53",
                "NIST 800-53", "NIST SP 800-53 Rev. 5", "CSF 2.0"

Must include: "duplicate effort"
  Also accepts: "duplicative effort", "redundancy", "duplicate controls",
                "overlapping controls", "eliminate overlap",
                "reduce redundancy", "control overlap"

Must include: "single implementation"
  Also accepts: "unified implementation", "consolidated implementation",
                "common control", "shared control"
```

### Forbidden Framework Context Awareness

The assertion scorer does NOT blindly flag forbidden terms. It checks surrounding
context (2 lines before the match). If the context contains exclusion language,
the match is ignored:

```
Exclusion patterns that suppress a forbidden match:
  - "not applicable"
  - "not in scope"
  - "out of scope"
  - "does not apply"
  - "excluded"
  - "only if"
  - "no eu/phi/payment/cardholder/financial/federal/government/defense"

Example:
  Forbidden: "HIPAA"
  Response line: "HIPAA does not apply to this scenario"
  Result: IGNORED (exclusion context detected)

  Response line: "Implement HIPAA access controls"
  Result: FLAGGED (no exclusion context)
```

### Dimension-Weighted Scoring (aggregate)

Each test case is tagged with 1-3 rubric dimensions. After all cases run,
`score_eval.py` computes per-dimension averages:

```
Rubric Dimensions and Weights (must sum to 1.0):

  applicability_accuracy .... 20%   "Right frameworks for the scenario?"
  factual_correctness ....... 20%   "Are the facts correct?"
  actionability ............. 18%   "Is the guidance implementable?"
  adversarial_robustness .... 15%   "Does it resist traps?"
  control_deduplication ..... 12%   "Does it consolidate overlaps?"
  scope_discipline .......... 10%   "Does it avoid over-scoping?"
  efficiency ................  5%   "Is it prioritized by impact?"
                              ----
                              100%
```

When the judge is enabled, each dimension gets a blended score:

```
  blended = (0.5 * assertion_score) + (0.5 * judge_score)
```

---

## 8. Decision Gate

The system uses a binary adopt/reject gate. ALL of these must be true:

```
+-----+----------------------------------------+-----------+
|  #  | Threshold                              | Minimum   |
+-----+----------------------------------------+-----------+
|  1  | Pass rate (cases with perfect score)    | >= 80%    |
|  2  | Average assertion score                 | >= 0.85   |
|  3  | Weighted blended dimension score        | >= 0.85   |
|  4  | Each dimension's blended average        | >= 0.75   |
|  5  | Each dimension has at least N cases     | >= 4      |
|  6  | Total test cases run                    | >= 30     |
|  7  | Each suite has at least N cases         | >= 5      |
|  8  | Judge average semantic score            | >= 0.80   |
|  9  | Hallucination flags in adversarial suite| = 0       |
+-----+----------------------------------------+-----------+

   ALL pass  -->  meets_decision_gate = true   --> safe to adopt
   ANY fail  -->  meets_decision_gate = false  --> do not adopt
```

Thresholds 6 and 7 are sample-size guardrails: they prevent the gate from
passing on a run with too few test cases (which could pass by luck).

Threshold 9 is a zero-tolerance policy: if the judge detects ANY hallucinated
regulation or fabricated fact in the adversarial suite, the entire eval fails.

---

## 9. What the Judge Looks For

The Opus judge evaluates each response on the specific dimensions tagged to that
test case. Here are the dimension definitions it receives:

```
applicability_accuracy:
  "Correctly identifies which frameworks apply based on jurisdiction,
   industry, and data types, and correctly excludes inapplicable frameworks."

factual_correctness:
  "All regulatory citations, effective dates, thresholds, and requirements
   are factually accurate. No hallucinated or invented information."

actionability:
  "Provides specific, implementable guidance with concrete steps, timelines,
   and technical controls rather than generic advice."

control_deduplication:
  "Identifies overlapping controls across frameworks and recommends
   consolidated implementations rather than duplicative work."

scope_discipline:
  "Avoids recommending frameworks, regulations, or controls not relevant
   to the scenario. Resists over-scoping."

efficiency:
  "Prioritises recommendations by impact and effort. Avoids unnecessary
   complexity."

adversarial_robustness:
  "Correctly handles edge cases: flags unknown or unverifiable regulations,
   respects temporal boundaries (e.g. as-of dates), refuses to validate
   fabricated claims, and resists prompt-based over-scoping pressure."
```

For adversarial test cases, the judge also receives hints explaining what the
trap is (e.g. "GDTPA is a fabricated regulation"), so it can specifically check
whether the AI fell for it.

---

## 10. Known Limitations

**Things this eval DOES catch:**
- Wrong framework for the jurisdiction
- Missing expected framework
- Over-scoping (recommending inapplicable frameworks)
- Missing required content (gap analysis, control mapping, etc.)
- Fabricated regulation traps (adversarial suite)
- Wrong PCI DSS levels, wrong DORA effective dates

**Things this eval does NOT catch (yet):**
- Subtle factual errors in implementation guidance (partially covered by judge)
- Whether cited effective dates are exactly correct (no date extraction assertions)
- Whether the report would pass review by a real auditor
- Performance across different AI models or temperatures
- Regression between runs (no automated diff tooling)
- Whether the report is useful in a real-world compliance program

**Assumptions requiring your domain review:**
- Are the expected_frameworks for each scenario correct?
- Are the forbidden_frameworks for each scenario correct?
- Are the must_include terms the right things to require?
- Are the adversarial traps well-designed and unambiguous?
- Are the rubric dimension weights appropriate for enterprise use?
- Is 80% pass rate the right adoption threshold?

---

## Appendix: How to Run

```bash
# Setup
cd security-compliance-v2
export ANTHROPIC_API_KEY=your-key

# Full run with judge (45 cases, ~30 min, ~$5-10)
uv run python scripts/run_eval.py \
  --all --strict --enable-judge --prompt-style compact --out tests/results

# Score the run (instant, free)
uv run python scripts/score_eval.py \
  --results tests/results/<timestamp>/results.jsonl \
  --rubric tests/rubric/scoring_rubric.json \
  --out tests/results/<timestamp>/score.json

# Resume a crashed run
uv run python scripts/run_eval.py \
  --all --strict --enable-judge --out tests/results \
  --resume tests/results/<timestamp>
```
