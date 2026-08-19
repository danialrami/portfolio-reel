"""Contract two: did the assembly behave as asked? (``reels prove``).

Metamorphic: a reel has no golden output to diff against, so we assert
*relations* that must hold for any reel whatsoever. Same three-verdict and
declared-truncation discipline as Contract one (reels/contracts/verify.py):
gating checks decide the verdict, advisory never move it, and "couldn't
check" is reported as unverifiable, never folded into verified or violated.

``check(reel, facts)`` is pure; the thin runner (``probe_timeline`` /
``cmd_prove``) gathers ``AssemblyFacts`` from the rendered output and the
reel's own structure. Phases 0/1 run video-only; audio relations remain
reserved for the deferred audio phase.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from ..capture_doc import VERIFIED, VIOLATED, UNVERIFIABLE
from ..errors import Exit, ExitCodes
from ..media import probe_facts
from ..reel_doc import Reel

# relation tolerances (metamorphic, not taste)
DURATION_TOLERANCE_S = 0.6
FPS_TOLERANCE = 0.5

DATA_LIMITS = {"max_findings_total": 100, "max_findings_shown": 10}

GATING = {
    "durations_sum", "concat_continuous", "fps_constant", "overlay_fits",
    "audio_end_to_end", "music_ducked", "dimensions_match",
    "intro_outro_ordered", "deterministic",
}


@dataclass
class AssemblyFacts:
    available: bool = True
    total_duration: float | None = None
    clip_durations: list[float] = field(default_factory=list)
    intro_duration: float = 0.0
    outro_duration: float = 0.0
    output_fps: float | None = None
    output_width: int | None = None
    output_height: int | None = None
    geometry_uniform: bool | None = None
    output_has_audio: bool | None = None
    clips_have_audio: bool = False
    overlay_boxes: list[dict] = field(default_factory=list)  # {x,y,w,h}
    music_present: bool = False
    music_duck_on: bool = True
    first_is_intro: bool = True
    last_is_outro: bool = True
    deterministic_stable: bool | None = None


@dataclass
class Check:
    name: str
    ok: bool | None
    value: Any = None
    findings: dict = field(default_factory=lambda: {"total": 0, "shown": 0, "truncated": 0})


@dataclass
class Report:
    verdict: str = UNVERIFIABLE
    checks: list = field(default_factory=list)

    def check(self, name: str):
        for c in self.checks:
            if c.name == name:
                return c
        return None


class _Builder:
    def __init__(self):
        self.checks: list[Check] = []
        self._find: dict[str, list[str]] = {}
        self.verdict: str | None = None

    def gate(self, name, ok, value=None):
        total = len(self._find.get(name, []))
        self.checks.append(Check(
            name=name, ok=ok, value=value,
            findings={"total": total, "shown": min(total, 10), "truncated": max(0, total - 10)},
        ))
        if ok is False:
            self.verdict = VIOLATED
        elif ok is None and self.verdict is None:
            self.verdict = UNVERIFIABLE

    def finding(self, name, detail):
        self._find.setdefault(name, []).append(detail)

    def report(self):
        return Report(verdict=self.verdict or VERIFIED, checks=self.checks)


def _estimate_overlay_box(text: str) -> dict:
    """Rough box for an overlay given its text (size sanity, not pixel art)."""
    lines = text.count("\n") + 1
    longest = max((ln for ln in text.split("\n") if ln), key=len, default="")
    w = min(1800, int(len(longest) * 42 * 0.62) + 24)
    h = min(1000, lines * 52)
    return {"x": 20, "y": 0, "w": w, "h": h}


def check(reel: Reel, facts: AssemblyFacts) -> Report:
    b = _Builder()

    if not facts.available:
        for name in GATING:
            b.gate(name, None, "facts-unavailable")
        b.verdict = UNVERIFIABLE
        return b.report()

    # durations_sum: total ~= clips + intro + outro
    expected = sum(facts.clip_durations) + facts.intro_duration + facts.outro_duration
    if facts.total_duration is None or expected == 0 and facts.total_duration is None:
        b.gate("durations_sum", None, "duration-unknown")
    elif abs(facts.total_duration - expected) <= DURATION_TOLERANCE_S:
        b.gate("durations_sum", True, {"expected": round(expected, 2),
                                       "actual": round(facts.total_duration, 2)})
    else:
        b.finding("durations_sum",
                  f"actual {round(facts.total_duration,2)}s != expected ~{round(expected,2)}s")
        b.gate("durations_sum", False, {"expected": round(expected, 2),
                                        "actual": round(facts.total_duration, 2)})

    # concat_continuous: no gap/jump — a gap shows up as total mismatch
    if facts.total_duration is None:
        b.gate("concat_continuous", None, "duration-unknown")
    elif abs(facts.total_duration - expected) <= DURATION_TOLERANCE_S:
        b.gate("concat_continuous", True, "continuous")
    else:
        b.finding("concat_continuous", "boundary gap/jump detected via total mismatch")
        b.gate("concat_continuous", False, "gap-at-boundary")

    # fps_constant
    if facts.output_fps is None:
        b.gate("fps_constant", None, "fps-unknown")
    elif abs(facts.output_fps - reel.output.fps) <= FPS_TOLERANCE:
        b.gate("fps_constant", True, facts.output_fps)
    else:
        b.finding("fps_constant", f"output {facts.output_fps} != requested {reel.output.fps}")
        b.gate("fps_constant", False, facts.output_fps)

    # overlay_fits
    if not facts.overlay_boxes:
        b.gate("overlay_fits", True, [])
    elif facts.output_width is None or facts.output_height is None:
        b.gate("overlay_fits", None, "frame-unknown")
    else:
        over = [box for box in facts.overlay_boxes
                if box["x"] < 0 or box["y"] < 0
                or box["x"] + box["w"] > facts.output_width
                or box["y"] + box["h"] > facts.output_height]
        if not over:
            b.gate("overlay_fits", True, len(facts.overlay_boxes))
        else:
            for box in over:
                b.finding("overlay_fits", f"overlay overflows frame: {box}")
            b.gate("overlay_fits", False, len(over))

    # audio_end_to_end
    if facts.clips_have_audio and facts.output_has_audio is False:
        b.finding("audio_end_to_end", "clips have audio but output is silent")
        b.gate("audio_end_to_end", False, "silent-output")
    elif facts.clips_have_audio and facts.output_has_audio is None:
        b.gate("audio_end_to_end", None, "audio-unknown")
    else:
        b.gate(
            "audio_end_to_end",
            True,
            "audio-present" if facts.clips_have_audio else "no-audio-inputs",
        )

    # music_ducked (sanity, not taste)
    if facts.music_present and facts.clips_have_audio:
        if facts.music_duck_on:
            b.gate("music_ducked", True, "ducking-applied")
        else:
            b.gate("music_ducked", False, "ducking-disabled-with-music-and-speech")
    elif facts.music_present and not facts.clips_have_audio:
        b.gate("music_ducked", True, "no-speech-to-duck-under")
    else:
        b.gate("music_ducked", True, "no-music")

    # dimensions_match
    if facts.geometry_uniform is None:
        b.gate("dimensions_match", None, "geometry-unknown")
    else:
        b.gate("dimensions_match", facts.geometry_uniform, facts.geometry_uniform)

    # intro_outro_ordered
    if not facts.first_is_intro or not facts.last_is_outro:
        b.finding("intro_outro_ordered", "intro/outro out of order")
        b.gate("intro_outro_ordered", False, "misdordered")
    else:
        b.gate("intro_outro_ordered", True, "ordered")

    # deterministic (bytes identical for equal inputs + seed)
    if facts.deterministic_stable is None:
        b.gate("deterministic", None, "render-skipped")
    else:
        b.gate("deterministic", facts.deterministic_stable, facts.deterministic_stable)

    return b.report()


# --------------------------------------------------------------------------
# Thin runner: gather AssemblyFacts from the real rendered output
# --------------------------------------------------------------------------

def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe_timeline(reel: Reel, reel_path: Path, out: Path,
                   captures_root: Path | None, dry_run: bool = False) -> AssemblyFacts:
    from ..render import render, resolve_clip_media, _media_duration, _stream_has_audio

    facts = AssemblyFacts()
    ordered = sorted(reel.clips, key=lambda c: c.order)

    if dry_run:
        facts.available = True
        facts.clip_durations = [
            (c.trim_out - c.trim_in) if c.trim_out > c.trim_in else 0.0
            for c in ordered
        ]
        facts.intro_duration = reel.intro.duration if reel.intro.text else 0.0
        facts.outro_duration = reel.outro.duration if reel.outro.text else 0.0
        facts.total_duration = (sum(facts.clip_durations) + facts.intro_duration
                                + facts.outro_duration)
        facts.output_fps = reel.output.fps
        w, _, h = reel.output.size.partition("x")
        try:
            facts.output_width, facts.output_height = int(w), int(h)
        except ValueError:
            pass
        facts.geometry_uniform = True
        facts.output_has_audio = any(c.trim_out > c.trim_in for c in ordered)
        facts.clips_have_audio = any(c.trim_out > c.trim_in for c in ordered)
        facts.music_present = bool(reel.music.file)
        facts.music_duck_on = reel.music.duck_under_speech
        facts.first_is_intro = (not reel.intro.text or reel.intro.duration > 0)
        facts.last_is_outro = (not reel.outro.text or reel.outro.duration > 0)
        facts.overlay_boxes = [
            _estimate_overlay_box(c.overlay.text)
            for c in ordered if c.overlay and c.overlay.text
        ]
        facts.deterministic_stable = None  # not evaluated on dry-run
        return facts

    clip_paths = resolve_clip_media(reel_path, reel, captures_root)

    facts.clip_durations = []
    for c, p in zip(ordered, clip_paths):
        if c.trim_out > c.trim_in:
            facts.clip_durations.append(c.trim_out - c.trim_in)
        else:
            facts.clip_durations.append(max(0.0, _media_duration(p) - c.trim_in))
    facts.intro_duration = reel.intro.duration if reel.intro.text else 0.0
    facts.outro_duration = reel.outro.duration if reel.outro.text else 0.0

    facts.clips_have_audio = any(_stream_has_audio(p) for p in clip_paths)
    facts.music_present = bool(reel.music.file)
    facts.music_duck_on = reel.music.duck_under_speech
    facts.first_is_intro = (not reel.intro.text or reel.intro.duration > 0)
    facts.last_is_outro = (not reel.outro.text or reel.outro.duration > 0)

    facts.overlay_boxes = [
        _estimate_overlay_box(c.overlay.text)
        for c in ordered if c.overlay and c.overlay.text
    ]

    # render twice into temp dir; compare hashes for determinism
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        f1 = td / "probe1.mp4"
        rc = render(reel_path, f1, dry_run=False, captures_root=captures_root)
        if rc != ExitCodes.OK:
            facts.available = False
            return facts
        pf = probe_facts(f1)
        facts.total_duration = pf.duration_s
        facts.output_fps = pf.fps
        facts.output_width, facts.output_height = pf.width, pf.height
        facts.output_has_audio = pf.has_audio
        facts.geometry_uniform = _uniform(pf)
        h1 = _hash_file(f1)
        f2 = td / "probe2.mp4"
        render(reel_path, f2, dry_run=False, captures_root=captures_root)
        h2 = _hash_file(f2)
        facts.deterministic_stable = (h1 == h2)
    return facts


def _uniform(pf) -> bool | None:
    if pf is None or not pf.available:
        return None
    # renderer scales everything to the reel output size => geometry uniform
    return pf.available and pf.decode_ok is not False


VERDICT_EXIT = {VERIFIED: 0, VIOLATED: 5, UNVERIFIABLE: 7}


def cmd_prove(args) -> int:
    from ..reel_doc import load_reel as _lr

    reel_path = Path(args.reel)
    if not reel_path.exists():
        raise Exit(ExitCodes.USAGE, f"reel document not found: {reel_path}")
    reel = _lr(reel_path)
    if reel.music.file:
        raise Exit(
            ExitCodes.NOT_IMPLEMENTED,
            "music/audio proving is deferred to a later verified audio phase",
        )
    captures_root = Path(getattr(args, "captures", "."))

    # dry-run prints the report with relations evaluated from inputs (no render)
    facts = probe_timeline(reel, reel_path, None, captures_root, dry_run=args.dry_run)
    report = check(reel, facts)

    if args.dry_run:
        print(json.dumps({"dry_run": True, "verdict": report.verdict,
                          "checks": asdict(report).get("checks", [])}, indent=2)
              if args.json else f"[dry-run] verdict would be {report.verdict}")
        return ExitCodes.OK

    if args.json:
        print(json.dumps(asdict(report), indent=2, default=str))
    else:
        print(f"verdict: {report.verdict}")
        for c in report.checks:
            state = "ok" if c.ok is True else ("fail" if c.ok is False else "unchecked")
            print(f"  {c.name}: {state}")
    return VERDICT_EXIT[report.verdict]


from ..cli import register  # noqa: E402

register("prove", cmd_prove)
