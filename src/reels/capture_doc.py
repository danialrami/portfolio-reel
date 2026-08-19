"""Capture Document: the normalised, typed statement of what a capture *is*.

One schema, many consumers (CLI, PWA, future workchain steps). Parsing fills
every missing default explicitly (never partial state), normalises paths, and
never raises on malformed input — malformed JSON or an unknown schema_version
yields a ``parses_clean=false`` verdict rather than a crash, per the
"proven, not exited 0" posture.

This module does *no* media IO (that is reels/media.py, Unit 04) and no
acquisition (Unit 03).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = 1

# verification.verdict vocabulary
VERIFIED = "verified"
VIOLATED = "violated"
UNVERIFIABLE = "unverifiable"


# --------------------------------------------------------------------------
# Nested documents
# --------------------------------------------------------------------------

@dataclass
class Source:
    platform: str = ""      # wayland | x11 | win | mac
    tool: str = ""          # wl-screenrec | wf-recorder | ffmpeg:gdigrab | ...
    region: str = ""        # monitor:0 | 1920x1080+0+0 | window:<id>


@dataclass
class Requested:
    fps: int = 30
    codec: str = "h264"
    audio: bool = False
    mic: bool = False
    out: str = "./shots"


@dataclass
class Captured:
    fps: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_s: Optional[float] = None
    decode_ok: Optional[bool] = None
    has_audio: Optional[bool] = None
    frames: Optional[int] = None
    mean_luma: Optional[float] = None
    integrated_lufs: Optional[float] = None
    peak_dbfs: Optional[float] = None


@dataclass
class Check:
    name: str
    # Tri-state is deliberate: None means the check was not evaluable.
    ok: Optional[bool]
    value: Any = None
    findings: dict = field(default_factory=lambda: {"total": 0, "shown": 0, "truncated": 0})


@dataclass
class Verification:
    verdict: str = UNVERIFIABLE
    checks: list = field(default_factory=list)


@dataclass
class Capture:
    schema_version: int = SCHEMA_VERSION
    capture_id: str = ""
    created: str = ""
    source: Source = field(default_factory=Source)
    requested: Requested = field(default_factory=Requested)
    captured: Captured = field(default_factory=Captured)
    file: str = ""
    content_sha256: str = ""
    reel_id: str = ""
    verification: Verification = field(default_factory=Verification)


# --------------------------------------------------------------------------
# Schema validation
# --------------------------------------------------------------------------

def validate(c: Capture) -> list[str]:
    """Return a list of schema violations (empty if the doc is clean)."""
    problems: list[str] = []
    if c.schema_version != SCHEMA_VERSION:
        problems.append(f"unsupported schema_version {c.schema_version}")
    if not c.capture_id:
        problems.append("missing capture_id")
    if not c.file:
        problems.append("missing file")
    if c.verification.verdict not in {VERIFIED, VIOLATED, UNVERIFIABLE}:
        problems.append(f"invalid verification.verdict {c.verification.verdict!r}")
    return problems


def _verdict_with(c: Capture, check_ok: bool, name: str = "parses_clean") -> Capture:
    """Stamp a ``parses_clean`` (or named) check onto the doc and set verdict.

    A failed check forces ``violated``; a passed check leaves the existing
    verdict intact (a schema-valid but unverified doc stays ``unverifiable``;
    a stored ``verified`` doc stays ``verified``).
    """
    checks = [ch for ch in c.verification.checks if ch.name != name]
    checks.append(Check(name=name, ok=check_ok))
    if not check_ok:
        c.verification.verdict = VIOLATED
    elif c.verification.verdict not in {VERIFIED, VIOLATED, UNVERIFIABLE}:
        c.verification.verdict = UNVERIFIABLE
    c.verification.verdict = c.verification.verdict or UNVERIFIABLE
    c.verification.checks = checks
    return c


# --------------------------------------------------------------------------
# Parsing / serialisation
# --------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _apply(data: dict, cls: type, dest: Any) -> Any:
    """Overlay ``data`` keys onto a default instance of a nested dataclass."""
    for key, value in data.items():
        if hasattr(dest, key):
            setattr(dest, key, value)
    return dest


def parse_capture(text: str) -> Capture:
    """Parse capture JSON into a typed ``Capture``.

    Never raises: malformed JSON or an unknown schema_version returns a
    ``Capture`` whose verification carries ``parses_clean: false`` and verdict
    ``violated``. Valid documents get every missing default filled explicitly.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return _verdict_with(Capture(), check_ok=False)
    if not isinstance(data, dict):
        return _verdict_with(Capture(), check_ok=False)

    schema_version = data.get("schema_version", SCHEMA_VERSION)
    if schema_version != SCHEMA_VERSION:
        return _verdict_with(Capture(), check_ok=False)

    c = Capture(schema_version=SCHEMA_VERSION)
    c.capture_id = data.get("capture_id", "")
    c.created = data.get("created", _now())
    c.file = data.get("file", "")
    c.content_sha256 = data.get("content_sha256", "")
    c.reel_id = data.get("reel_id", "")

    if isinstance(data.get("source"), dict):
        _apply(data["source"], Source, c.source)
    if isinstance(data.get("requested"), dict):
        _apply(data["requested"], Requested, c.requested)
    if isinstance(data.get("captured"), dict):
        _apply(data["captured"], Captured, c.captured)
    if isinstance(data.get("verification"), dict):
        v = data["verification"]
        c.verification.verdict = v.get("verdict", UNVERIFIABLE)
        for ch in v.get("checks", []) or []:
            if isinstance(ch, dict):
                check_ok = ch.get("ok")
                if not isinstance(check_ok, bool) and check_ok is not None:
                    check_ok = bool(check_ok)
                c.verification.checks.append(
                    Check(
                        name=ch.get("name", ""),
                        ok=check_ok,
                        value=ch.get("value"),
                        findings=ch.get("findings") or {"total": 0, "shown": 0, "truncated": 0},
                    )
                )

    problems = validate(c)
    return _verdict_with(c, check_ok=not problems)


def to_json(c: Capture) -> str:
    return json.dumps(asdict(c), indent=2, sort_keys=False)


def load_capture(path: Path) -> Capture:
    """Read a capture document, resolving ``file`` relative to its directory."""
    path = Path(path)
    c = parse_capture(path.read_text())
    if c.file:
        c.file = str((path.parent / c.file).resolve())
    return c


def save_capture(path: Path, c: Capture) -> None:
    Path(path).write_text(to_json(c) + "\n")
