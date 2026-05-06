"""K4 scaffold — Content-injection templates.

Authorizing section: runbook-05 §1 Phase K (U5).

# TODO(K4): implement inject_template(target_bytes, template_bytes, mapping) -> bytes
# where the template carries placeholder tokens (e.g. {{client_name}}) and
# `mapping` is a dict of substitutions. Walks word/document.xml and replaces
# matching runs while preserving formatting.
"""

from __future__ import annotations
