---
description: "Run compliance evaluation suites against security-compliance-v2 with reproducible scoring"
argument-hint: "<suite-path|all> [--runner internal|api] [--strict]"
allowed-tools:
  ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]
---

# Compliance Evaluation Runner

Run the packaged evaluation suites under `tests/suites/` and produce scored results.

## Inputs

- `$ARGUMENTS` supports:
  - `all` or a suite path
  - `--runner internal|api`
  - `--strict` for hard assertion behavior

## Behavior

1. Resolve suite selection:
   - `all` => all files in `tests/suites/*.jsonl`
   - Otherwise => use provided suite path
2. Create output directory: `tests/results/<timestamp>/`
3. For each test case:
   - Execute assessment generation using `commands/compliance-check.md` behavior.
   - Score output against case assertions:
     - `expected_frameworks`
     - `forbidden_frameworks`
     - `must_include`
     - `must_not_include`
4. Write:
   - `tests/results/<timestamp>/results.jsonl`
   - `tests/results/<timestamp>/summary.md`

## Runner Modes

### internal

- Use local in-session execution for each test case.
- Good for Claude Desktop / Claude Code interactive benchmarking.

### api

- Use script runner:

```bash
python3 scripts/run_eval.py --all --out tests/results
```

or

```bash
python3 scripts/run_eval.py --suite tests/suites/<file>.jsonl --out tests/results
```

## Scoring Rules

- Base score = proportion of assertions passed.
- Failing any forbidden-framework or must-not-include assertion is a hard failure if `--strict` is enabled.
- Include pass/fail status and failure reason per case.

## Final Response

Return:

1. Overall pass rate
2. Per-suite pass rate
3. Top 5 failure patterns
4. Recommended next prompt changes
