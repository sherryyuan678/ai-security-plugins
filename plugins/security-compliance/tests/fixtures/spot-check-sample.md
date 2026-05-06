---
type: compliance-spot-check
date: 2026-05-06
scenario: "Fintech app handling EU customer payment data and offering AI-driven credit decisions"
applicable_frameworks:
  - GDPR
  - PCI_DSS
  - EU_AI_ACT
  - SOC2
jurisdictions:
  - EU
  - UK
industry: "fintech"
tags: [compliance, spot-check, gdpr, pci_dss, eu_ai_act, soc2]
---

# Compliance Spot-Check: Fintech App with EU Payment Data and AI Credit Decisions

> **Date:** 2026-05-06 | **Frameworks:** GDPR, PCI DSS, EU AI Act, SOC 2 | **Industry:** fintech

## TL;DR

- EU customers + payment data + automated credit decisions trigger four overlapping regimes simultaneously.
- GDPR Article 22 prohibitions on solely automated decisions with legal effects govern the credit-decision flow.
- PCI DSS 4.0.1 baseline applies to anything that transmits, stores, or processes the cardholder PAN.
- EU AI Act high-risk classification likely; full conformity assessment required before deployment.
- SOC 2 Type II is baseline for any SaaS handling external customer data.

## Table of Contents

- [Regulatory Applicability Assessment](#regulatory-applicability-assessment)
- [Compliance Gap Summary](#compliance-gap-summary)
- [Cross-Framework Control Map](#cross-framework-control-map)
- [Recommended Next Steps](#recommended-next-steps)

## Regulatory Applicability Assessment

GDPR applies because the system processes the personal data of identified EU customers. The credit-decision flow is solely automated processing producing legal effects, triggering Article 22 and DPIA obligations under Article 35.

PCI DSS 4.0.1 applies to all components that transmit, store, or process cardholder data. Tokenization and network segmentation define the scope of in-scope systems.

EU AI Act high-risk classification applies because the AI system makes credit-evaluation decisions about natural persons (Annex III §5(b)). This requires conformity assessment, technical documentation, and post-market monitoring.

SOC 2 Type II is baseline for a SaaS provider handling external customer data; trust service criteria CC6 (logical access) and CC7 (system operations) anchor the identity-control gap analysis.

## Compliance Gap Summary

The current design has a custom RBAC layer with no break-glass workflow, JIT credentials are not used for production access, automated credit decisions lack the GDPR Article 22 "human-in-the-loop" override, and PCI DSS 4.0.1 §8.3.6 password complexity controls are missing on the admin console.

## Cross-Framework Control Map

A single workload-identity federation implementation satisfies SOC 2 CC6.1 (logical access), GDPR Article 32 (security of processing), PCI DSS 4.0.1 §7.2 (least privilege), and EU AI Act §15(2) (cybersecurity for high-risk systems). Consolidating identity proofing through OIDC + SCIM avoids duplicate effort across the four regimes.

## Recommended Next Steps

1. Wire a human-in-the-loop override into the credit-decision flow within 30 days to satisfy GDPR Article 22.
2. Adopt workload-identity federation for production access within 30-90 days; retire static service-account keys.
3. Run a DPIA covering the credit-decision flow and the payment-data ingestion path within 60 days.
4. Engage an EU AI Act conformity-assessment partner; target 90-180 days for technical-documentation completion.
