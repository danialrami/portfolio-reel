"""Deterministic content identity (``reel-<hex>``).

The identity is a pure function of the file's bytes, so the same input always
yields the same id regardless of path, host, or time. Used by ``reels id`` and
as the ``reel_id`` provenance on capture documents.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

PREFIX = "reel"


def content_id(path: Path) -> str:
    """Return ``reel-<sha256 first 8>`` for the file at ``path``.

    Raises ``FileNotFoundError`` if the path does not resolve to a readable
    file. The digest is the lowercase hex of the first 8 bytes of the SHA-256
    of the file contents.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return f"{PREFIX}-{digest.hexdigest()[:8]}"


def reel_id_from_bytes(data: bytes) -> str:
    """Return ``reel-<hex>`` for raw bytes (used where no file exists yet)."""
    return f"{PREFIX}-{hashlib.sha256(data).hexdigest()[:8]}"
