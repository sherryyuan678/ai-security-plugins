# ai-security-plugins

Security and compliance plugins for Claude Cowork/Code.

**Author:** [Sherry Yuan](https://github.com/sherryyuan678) | [LinkedIn](https://www.linkedin.com/in/sherryyuan/)

## Available Plugins

| Plugin | Version | Description |
|--------|---------|-------------|
| [security-compliance](./plugins/security-compliance/) | 1.0.0 | Identity architecture validator for IAM, CIAM, RBAC, and workload-identity designs. Maps your authentication/authorization model (OAuth 2.x, OIDC, SAML, SCIM, ephemeral credentials, machine identity) to applicable regulatory frameworks (11 supported: GDPR, HIPAA, SOC 2, PCI DSS, ISO 27001, NIST CSF, CCPA/CPRA, DORA, EU AI Act, CMMC, FedRAMP), surfaces identity-specific compliance gaps, and recommends single-implementation control consolidation across frameworks. |

## Installation

### Install in Claude Cowork

In the Claude Desktop app:

1. Switch to the **Cowork** tab in the mode selector at the top.
2. Click **Customize** in the left sidebar.
3. Click **Browse plugins**, then select **Personal**.
4. Click the **+** button and select **Add marketplace from GitHub**.
5. Enter the repository URL: `https://github.com/sherryyuan678/ai-security-plugins`
6. Once the marketplace is added, install **security-compliance** from the
   marketplace's plugin list.

After install, just say `/security-compliance:spot-check <scenario>` — both
the markdown report and the DOCX summary will appear under
`.compliance-reports/`.

![Adding the plugin marketplace in Claude Cowork](./plugins/security-compliance/docs/claude-cowork-install.png)

### Install in Claude Code

```
/plugin marketplace add sherryyuan678/ai-security-plugins
/plugin install security-compliance@sherryyuan678-ai-security-plugins
```

After install, run `/security-compliance:spot-check <scenario>` to produce
the same paired markdown + DOCX deliverables.

## License

MIT
