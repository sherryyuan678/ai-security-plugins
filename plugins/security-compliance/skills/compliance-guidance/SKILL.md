---
name: compliance-guidance
description: "This skill should be used when the user asks conversational questions about regulatory compliance, data protection, security frameworks, or audit preparation. It provides concise inline guidance covering major frameworks (GDPR, HIPAA, SOC 2, PCI DSS, ISO 27001, NIST CSF, DORA, EU AI Act, and others). Typical triggers: 'what compliance frameworks apply to my business,' 'how do I prepare for a SOC 2 audit,' 'does GDPR apply to us,' 'DORA requirements for fintech,' 'EU AI Act risk classification,' 'do we need SOC 2,' 'am I compliant.' For full reports, directs users to spot-check or compliance-check commands."
version: 2.0.0
---

When the user asks about regulatory compliance, data protection, security frameworks, or audit preparation:

1. Use the framework version data injected by the resolve_frameworks hook
   as the source of truth for version numbers, effective dates, and
   publication dates. If hook-injected data is unavailable, fall back to
   running: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/select_framework_versions.py --as-of <YYYY-MM-DD> --format markdown`

2. Follow these scope discipline rules:
   - Only discuss frameworks that are applicable to the user's scenario.
   - Do NOT name inapplicable frameworks. Instead use phrasing like
     "No healthcare data obligations apply" rather than "HIPAA does not apply."
   - If you cannot verify a regulation is real and currently in force,
     flag it with REQUIRES VALIDATION.

3. Follow these baseline framework guidelines:
   - SOC 2 Type II is baseline for any SaaS, cloud, or technology service
     provider serving external customers.
   - ISO 27001 is baseline for organisations selling to enterprise customers.
   - NIST CSF is a standard risk-management framework for US-based organisations.
   - Do NOT recommend these for purely internal tools with no external customers
     or data processing obligations.

4. When discussing multiple frameworks, identify overlapping controls and
   recommend consolidated implementations to avoid duplicate effort.

5. **Output format — concise summary only.** Keep your inline response short
   and actionable. Use this format:

   ```
   **Applicable frameworks:**
   - **<Framework 1>** — <one-line rationale>
   - ...

   **Not applicable:** <brief scope boundary statement, e.g., "No healthcare
   data or federal/defense obligations identified">

   **Key guidance:**
   - <Most important point>
   - <Second point>
   - <Third point>
   ```

   Aim for 10-20 lines. Do NOT produce lengthy inline analyses. If the user
   needs more depth, direct them to the commands below.

6. For deeper analysis, suggest the user run:
   - `/security-compliance:spot-check <scenario>` — concise summary + detailed report file
   - `/security-compliance:compliance-check <scenario>` — full 8-step phased engagement with multiple deliverables
