"""K3 scaffold — Selective accept by author/change-type.

Authorizing section: runbook-05 §1 Phase K (U5).

# TODO(K3): implement accept_changes_filtered(target_bytes, predicate) -> bytes
# where predicate is Callable[[ChangeMeta], bool] receiving author, timestamp,
# and change-kind for each <w:ins>/<w:del>/<w:moveFrom>/<w:moveTo>. Only
# changes passing predicate are accepted; the rest stay marked.
"""

from __future__ import annotations
