"""Media facts runner: the thin IO layer the pure contracts consume.

``probe_facts`` runs ffprobe to learn duration/geometry/streams, decodes the
file to prove it is readable, and measures video mean luma via ffmpeg
``signalstats``. It never decides a verdict — it only gathers ``Facts`` that
``reels/contracts/verify.py`` consumes purely. Audio loudness measurement is
retained as a deferred phase implementation. Missing facts are reported as
``available=False`` (unverifiable), never folded into "fine".

Shared by verify (Unit 04) and prove (Unit 06) — later units only read it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .errors import Exit, ExitCodes


@dataclass
class Facts:
    available: bool = False
    duration_s: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    frames: int | None = None
    decode_ok: bool | None = None
    mean_luma: float | None = None
    has_audio: bool | None = None
    integrated_lufs: float | None = None
    peak_dbfs: float | None = None
    codecs: list[str] = field(default_factory=list)
    sample_geometry: list[tuple] = field(default_factory=list)  # (fps, w, h)


def _require(binary: str) -> None:
    if shutil.which(binary) is None:
        raise Exit(ExitCodes.MISSING_BINARY, f"required binary missing: {binary}")


def _ffprobe(path: Path) -> dict | None:
    _require("ffprobe")
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def _decode_check(path: Path) -> bool:
    _require("ffmpeg")
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
        capture_output=True, text=True,
    )
    return proc.returncode == 0


def _loudness(path: Path) -> tuple[float | None, float | None]:
    """Return (integrated_lufs, peak_dbfs) via ebur128, or (None, None)."""
    _require("ffmpeg")
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    text = proc.stderr
    lufs = None
    peak = None
    # take the LAST match: the integrated summary value, not the warm-up sample
    m = re.findall(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", text)
    if m:
        lufs = float(m[-1])
    m = re.findall(r"Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS", text)
    if m:
        peak = float(m[-1])
    return lufs, peak


def _video_brightness(path: Path) -> float | None:
    """Return mean frame luma (0..255) using ffmpeg signalstats.

    This is the phase-0/1 blankness signal. Audio loudness measurement remains
    intentionally deferred; keep that implementation below for the later audio
    phase rather than making video verification depend on an audio stream.
    """
    _require("ffmpeg")
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(path),
            "-map", "0:v:0", "-an", "-vf",
            "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
            "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    text = proc.stdout + proc.stderr
    values = re.findall(r"lavfi\.signalstats\.YAVG=([0-9]+(?:\.[0-9]+)?)", text)
    if not values:
        return None
    return sum(float(value) for value in values) / len(values)


def _avg_fps(av_fps: str | None) -> float | None:
    if not av_fps:
        return None
    try:
        num, _, den = av_fps.partition("/")
        return float(num) / float(den) if den else float(num)
    except (ValueError, ZeroDivisionError):
        return None


def probe_facts(path: Path) -> Facts:
    """Gather media facts for ``path``.

    Raises ``Exit(4)`` when ffprobe/ffmpeg are missing. Returns
    ``Facts(available=False)`` when the file is absent or unreadable
    (the caller maps that to ``unverifiable``).
    """
    path = Path(path)
    if not path.exists() or not path.is_file():
        return Facts()

    data = _ffprobe(path)
    if data is None:
        # file exists but ffprobe can't open it -> unverifiable, not "fine"
        return Facts(available=False)

    facts = Facts(available=True)
    streams = data.get("streams", []) or []
    fmt = data.get("format", {}) or {}

    try:
        facts.duration_s = float(fmt.get("duration"))
    except (TypeError, ValueError):
        facts.duration_s = None

    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video:
        facts.width = video.get("width")
        facts.height = video.get("height")
        facts.fps = _avg_fps(video.get("avg_frame_rate"))
        try:
            facts.frames = int(video.get("nb_frames")) if video.get("nb_frames") else None
        except (TypeError, ValueError):
            facts.frames = None
        if video.get("codec_name"):
            facts.codecs.append(video["codec_name"])
    if audio and audio.get("codec_name"):
        facts.codecs.append(audio["codec_name"])
    facts.has_audio = audio is not None

    for s in streams:
        if s.get("codec_type") == "video":
            fps = _avg_fps(s.get("avg_frame_rate"))
            facts.sample_geometry.append((fps, s.get("width"), s.get("height")))

    facts.decode_ok = _decode_check(path)
    facts.mean_luma = _video_brightness(path)
    # Deferred audio phase: when audio capture is promoted from advisory to a
    # verified feature, populate these fields with _loudness(path).
    # facts.integrated_lufs, facts.peak_dbfs = _loudness(path)
    return facts
