"""Shared test helpers for the security-compliance plugin.

pytest auto-loads ``conftest.py`` for fixtures/plugins. The functions below
are also importable as ``from conftest import …`` because pytest puts each
``conftest.py``'s parent directory on ``sys.path`` during collection in the
current pytest setup. If the import ever breaks across pytest configs,
convert these to ``@pytest.fixture`` instead.
"""

from __future__ import annotations

import zipfile
from pathlib import Path


def read_members(path: Path) -> dict[str, str]:
    """Return ``{member_name: utf-8 contents}`` for every XML member in a docx."""
    out: dict[str, str] = {}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.endswith(".xml") or name.endswith(".rels"):
                out[name] = zf.read(name).decode("utf-8")
    return out


def find_footer_xml(members: dict[str, str]) -> str:
    """Return the concatenated text of every ``word/footer*.xml`` member."""
    return "\n".join(v for k, v in members.items() if k.startswith("word/footer"))
