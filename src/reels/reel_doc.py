"""Reel Document: the timeline / assembly manifest (reel.json).

The Reel Document is the second unit-of-value document of the primitive (after
the Capture Document). It describes the assembled reel: output parameters,
style, intro/outro, background music, and an ordered list of trimmed clips
with overlays. Same discipline as the Capture Document — explicit defaults,
no-crash parse, path normalisation, three-verdict verification header.

This module does no assembly validation (Unit 06) and no rendering (Unit 07).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from .capture_doc import VERIFIED, VIOLATED, UNVERIFIABLE, Check

SCHEMA_VERSION = 1


@dataclass
class Output:
    filename: str = "Reel.mp4"
    fps: int = 30
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    size: str = "1920x1080"


@dataclass
class Style:
    font: str = "DejaVu-Sans-Bold"
    overlay_bg: str = "rgba(0,0,0,0.5)"
    fade_duration: float = 0.5


@dataclass
class IntroOutro:
    text: str = ""
    duration: float = 0.0


@dataclass
class Music:
    file: str = ""
    volume: float = 0.15
    duck_under_speech: bool = True


@dataclass
class Overlay:
    text: str = ""
    position: str = "bottom-left"


@dataclass
class ClipRef:
    capture_ref: str = ""
    trim_in: float = 0.0
    trim_out: float = 0.0
    order: int = 1
    overlay: Overlay = field(default_factory=Overlay)


@dataclass
class Verification:
    verdict: str = UNVERIFIABLE
    checks: list = field(default_factory=list)


@dataclass
class Reel:
    schema_version: int = SCHEMA_VERSION
    reel_id: str = ""
    output: Output = field(default_factory=Output)
    style: Style = field(default_factory=Style)
    intro: IntroOutro = field(default_factory=IntroOutro)
    outro: IntroOutro = field(default_factory=IntroOutro)
    music: Music = field(default_factory=Music)
    clips: list = field(default_factory=list)          # list[ClipRef]
    verification: Verification = field(default_factory=Verification)


def _apply(data: dict, dest: object) -> None:
    for key, value in data.items():
        if hasattr(dest, key):
            setattr(dest, key, value)


def validate(r: Reel) -> list[str]:
    problems: list[str] = []
    if r.schema_version != SCHEMA_VERSION:
        problems.append(f"unsupported schema_version {r.schema_version}")
    if r.output.fps <= 0:
        problems.append("output.fps must be > 0")
    if not r.output.filename:
        problems.append("missing output.filename")
    seen = set()
    for i, clip in enumerate(r.clips):
        if not clip.capture_ref:
            problems.append(f"clip[{i}] missing capture_ref")
        if clip.order in seen:
            pass  # duplicate orders are allowed (stable sort preserves them)
        seen.add(clip.order)
        if clip.trim_out < clip.trim_in:
            problems.append(f"clip[{i}] trim_out < trim_in")
    if r.verification.verdict not in {VERIFIED, VIOLATED, UNVERIFIABLE}:
        problems.append(f"invalid verification.verdict {r.verification.verdict!r}")
    return problems


def _compute_reel_id(r: Reel) -> str:
    """Deterministic reel identity from the timeline (stable across saves)."""
    canon = {
        "output": asdict(r.output),
        "intro": asdict(r.intro),
        "outro": asdict(r.outro),
        "music": asdict(r.music),
        "clips": [
            {
                "capture_ref": c.capture_ref,
                "trim_in": c.trim_in,
                "trim_out": c.trim_out,
                "order": c.order,
                "overlay": asdict(c.overlay),
            }
            for c in sorted(r.clips, key=lambda c: (c.order, c.capture_ref))
        ],
    }
    blob = json.dumps(canon, sort_keys=True, separators=(",", ":")).encode()
    return f"reel-{hashlib.sha256(blob).hexdigest()[:8]}"


def parse_reel(text: str) -> Reel:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return _mark_bad(Reel())
    if not isinstance(data, dict) or data.get("schema_version", 1) != SCHEMA_VERSION:
        return _mark_bad(Reel())

    r = Reel(schema_version=SCHEMA_VERSION)
    if isinstance(data.get("output"), dict):
        _apply(data["output"], r.output)
    if isinstance(data.get("style"), dict):
        _apply(data["style"], r.style)
    if isinstance(data.get("intro"), dict):
        _apply(data["intro"], r.intro)
    if isinstance(data.get("outro"), dict):
        _apply(data["outro"], r.outro)
    if isinstance(data.get("music"), dict):
        _apply(data["music"], r.music)
    for item in data.get("clips", []) or []:
        if not isinstance(item, dict):
            continue
        ov = Overlay()
        if isinstance(item.get("overlay"), dict):
            _apply(item["overlay"], ov)
        r.clips.append(
            ClipRef(
                capture_ref=item.get("capture_ref", ""),
                trim_in=item.get("trim_in", 0.0),
                trim_out=item.get("trim_out", 0.0),
                order=item.get("order", 1),
                overlay=ov,
            )
        )
    if isinstance(data.get("verification"), dict):
        v = data["verification"]
        r.verification.verdict = v.get("verdict", UNVERIFIABLE)
        for ch in v.get("checks", []) or []:
            if isinstance(ch, dict):
                r.verification.checks.append(
                    Check(name=ch.get("name", ""), ok=bool(ch.get("ok")))
                )

    problems = validate(r)
    if problems:
        return _mark_bad(r)
    if not r.reel_id:
        r.reel_id = _compute_reel_id(r)
    return r


def _mark_bad(r: Reel) -> Reel:
    r.verification.verdict = VIOLATED
    r.verification.checks = [c for c in r.verification.checks if c.name != "parses_clean"]
    r.verification.checks.insert(0, Check(name="parses_clean", ok=False))
    return r


def to_json(r: Reel) -> str:
    return json.dumps(asdict(r), indent=2, sort_keys=False)


def load_reel(path: Path) -> Reel:
    r = parse_reel(Path(path).read_text())
    # resolve music file relative to the reel document's directory
    if r.music.file:
        r.music.file = str((Path(path).parent / r.music.file).resolve())
    return r


def save_reel(path: Path, r: Reel) -> None:
    if not r.reel_id:
        r.reel_id = _compute_reel_id(r)
    Path(path).write_text(to_json(r) + "\n")
