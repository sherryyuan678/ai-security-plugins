"""K1 scaffold — In-memory accept-changes (Python OOXML walker).

Authorizing section: runbook-05 §1 Phase K (U5).

This module reserves the file path and API surface for a future runbook-06+
implementation. It is currently empty and imported nowhere.

# TODO(K1): implement accept_changes_inmemory(target_bytes: bytes) -> bytes
# that walks word/document.xml, drops <w:ins>/<w:del>/<w:moveFrom>/<w:moveTo>
# subtrees in-memory (no soffice subprocess), and returns rebuilt bytes.
# Replaces the on-disk soffice path for cases where LibreOffice isn't
# available or the user prefers a pure-Python pipeline.

K5: lift this module to a shared library when a second consumer appears.
"""

from __future__ import annotations
