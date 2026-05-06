"""Atomic, rollback-safe versioned-immutable promote for DOCX outputs.

Pattern source: Mike chatTools.ts:1006-1018 (UUID-keyed S3 objects, never
overwritten). Adapted to filesystem with rollback-safe sequence (audit fix
HIGH 11):
  1. Write+fsync new bytes to tempfile in target's parent dir.
  2. Move existing target to <stem>.versions/<iso>-<uuid8>.docx (atomic same-fs).
  3. os.replace(tempfile, target) (atomic same-fs).
  4. On step-3 failure, restore prior from .versions/ to target (best-effort).

K5: lift this module to a shared library when a second consumer appears.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

EXIT_OK = 0
EXIT_INPUT = 1
EXIT_WRITE = 2
EXIT_INTERNAL = 3
EXIT_DEPENDENCY = 4  # U4 — soffice/pandoc/etc missing


@dataclass
class PromoteResult:
    promoted_path: Path
    prior_version_path: Optional[Path]
    sha256: str


def _ts_uuid_filename() -> str:
    """ISO-timestamp-Z + 8-hex uuid4 (S5 — strict format)."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    suf = uuid.uuid4().hex[:8]
    return f"{ts}-{suf}.docx"


def _restore_prior(prior: Optional[Path], target: Path) -> None:
    """Best-effort rollback: move prior version back to target on rename failure."""
    if prior is None or not prior.exists():
        return
    try:
        os.replace(str(prior), str(target))
    except OSError:
        pass


def versioned_promote(target_path: Path, new_bytes: bytes) -> PromoteResult:
    """Promote new_bytes to target_path; archive prior to <stem>.versions/.

    Atomic and rollback-safe: a failed final rename leaves the prior version
    restored at the target path (best-effort).
    """
    target_path = Path(target_path)
    parent = target_path.parent
    versions_dir = parent / f"{target_path.stem}.versions"
    versions_dir.mkdir(exist_ok=True)

    if target_path.exists():
        if os.stat(target_path).st_dev != os.stat(versions_dir).st_dev:
            raise RuntimeError(
                f"cross-filesystem rename refused: target={target_path} "
                f"versions_dir={versions_dir}"
            )

    fd, tmp = tempfile.mkstemp(prefix=".tmp.", suffix=".docx", dir=str(parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(new_bytes)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    prior: Optional[Path] = None
    if target_path.exists():
        prior = versions_dir / _ts_uuid_filename()
        try:
            os.replace(str(target_path), str(prior))
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    try:
        os.replace(tmp, str(target_path))
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        _restore_prior(prior, target_path)
        raise

    return PromoteResult(
        promoted_path=target_path,
        prior_version_path=prior,
        sha256=hashlib.sha256(new_bytes).hexdigest(),
    )
