---
description: Apply a template's styling to a docx OR accept all tracked changes
argument-hint: (--apply-template <T>|--accept-changes) <target.docx>
allowed-tools: Bash, Read, Write, Edit
---

# /edit-docx — Apply a template OR accept tracked changes

This command runs the `security-compliance` plugin's edit-docx pipeline. It
either grafts a template's visual styling onto a target docx
(`--apply-template`) or strips every tracked change from a docx
(`--accept-changes`).

## Workflow

1. **Resolve directory** — confirm the user's `cwd` contains the target
   `.docx`. If not, ask the user where to look.
2. **Resolve target + template** — read the `argument-hint` to extract paths.
3. **Preflight** — for `--accept-changes`, verify `soffice --version`
   succeeds. The plugin's `SessionStart` hook already probes for LibreOffice
   and emits a `systemMessage` if missing; this is belt-and-brace.
4. **Confirm intent** — the operation is destructive (target file is
   replaced). State the operation explicitly to the user before invoking:
   "I will replace `<target>.docx` with the styled version. The current file
   will be moved to `<target>.versions/<timestamp>-<uuid>.docx` and remain
   accessible. Confirm?"
5. **Invoke** — run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/edit_docx.py` with
   the resolved arguments. For `--apply-template`, pass
   `--apply-template <T> <target>`. For `--accept-changes`, pass
   `--accept-changes <target>`.
6. **Present result** — show the contents of `<target>.docx.report.json`
   (per-component graft + validation status) AND list the contents of
   `<target>.versions/` so the user can see the version history.

## Exit codes

- `0` — success
- `1` — bad input (missing file, malformed args)
- `2` — write error (filesystem, permissions)
- `3` — internal error (graft / validation failed)
- `4` — dependency missing (LibreOffice / `soffice`)

## Word fidelity contract

The pipeline preserves the following document features through a graft:

| Component | Behavior |
|---|---|
| `word/styles.xml` | Grafted from template |
| `word/theme/theme1.xml` | Grafted from template |
| `word/header*.xml` (+ rels) | Grafted from template (dynamic names) |
| `word/footer*.xml` (+ rels) | Grafted from template (dynamic names) |
| `[Content_Types].xml` overrides | Merged (template's header/footer overrides absorbed) |
| `word/numbering.xml` | **PRESERVED** (target wins) |
| `word/media/*` | Grafted from template (binary) |
| Tracked changes (`<w:ins>` etc.) | Removed by `--accept-changes`; preserved by `--apply-template` |
