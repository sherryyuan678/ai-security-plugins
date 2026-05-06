#!/usr/bin/env bash
# Cowork environment setup script for the security-compliance plugin.
#
# Paste this into your Cowork environment's "Setup script" field
# (claude.ai/code -> environment selector -> settings icon -> Setup script).
#
# Installs:
#   - LibreOffice (provides `soffice` for --accept-changes)
#   - gh CLI (for PR/issue commands; needs $GH_TOKEN env var separately)
#   - python-docx, pytest, lxml (in case the cached environment ages out)
#
# Runtime: ~3-4 minutes on first run; cached afterward.

set -euo pipefail

# Run independent installs in parallel where possible to stay under Cowork's
# ~5 minute setup-script budget.
apt update
apt install -y libreoffice gh &
APT_PID=$!

# Lazy-install Python deps (most are pre-installed but we belt-and-brace).
python3 -m pip install --upgrade pip >/dev/null 2>&1 || true
python3 -m pip install python-docx pytest lxml >/dev/null 2>&1 || true

wait "$APT_PID"

# Verify tools are on PATH
command -v soffice >/dev/null || { echo "FATAL: soffice not on PATH after install" >&2; exit 1; }
command -v gh      >/dev/null || { echo "WARN: gh not on PATH (PR commands will fail)" >&2; }
python3 -c "import docx, pytest, lxml" || { echo "FATAL: python deps missing" >&2; exit 1; }

echo "security-compliance Cowork setup: OK"
echo "  soffice : $(soffice --version | head -1)"
echo "  gh      : $(gh --version | head -1)"
echo "  python  : $(python3 --version)"
