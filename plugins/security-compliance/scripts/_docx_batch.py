"""K2 scaffold — Multi-file batch mode.

Authorizing section: runbook-05 §1 Phase K (U5).

# TODO(K2): implement run_manifest(manifest_path: Path) -> BatchReport
# that reads a YAML/JSON manifest of {target, template, mode} entries
# and runs edit_docx over each. BatchReport aggregates per-file
# {component, status, reason} entries from each graft + validation.
"""

from __future__ import annotations
