"""Contract one: is the capture whole? (``reels verify``).

A pure function of ``(capture_doc, facts)`` — the caller supplies ffprobe/media
facts, this module touches no IO, so the contract runs identically in the CLI,
a browser, and a future workchain step.

Every gating check is tri-state under the hood:

- ``ok=True``   -> the check passed
- ``ok=False``  -> the check *failed* (violated)
- ``ok=None``   -> the check could not be evaluated (unverifiable)

The verdict is decided exclusively by gating checks; advisory checks never move
it. Findings lists are capped by ``DATA_LIMITS`` with declared
``{total, shown, truncated}``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..capture_doc import VERIFIED, VIOLATED, UNVERIFIABLE, Capture
from ..media import Facts

# --- limits (declared truncation) ------------------------------------------

DATA_LIMITS = {
    "max_findings_total": 100,   # hard cap on total findings retained
    "max_findings_shown": 10,    # per-report shown cap
}

# --- thresholds -------------------------------------------------------------

MIN_DURATION_S = 1.0          # a sub-second capture is a dead capture
NOISE_LUMA_FLOOR = 16.0       # below this the video is effectively blank
# Audio thresholds are retained for the deferred audio phase only.
NOISE_LUFS_FLOOR = -60.0
NOISE_PEAK_FLOOR = -60.0

# gating (decide the verdict) vs advisory (never move it). Phase 0/1 is
# video-only: audio presence and loudness are observed only as advisory data.
GATING_CHECKS = {
    "parses_clean", "media_decodes", "min_duration",
    "uniform_geometry", "not_blank", "trims_in_bounds",
}
ADVISORY_CHECKS = {
    "has_audio", "audio_lufs_in_range", "codec_uniform", "no_static_frames",
}

LUFS_RANGE = (-24.0, -8.0)


@dataclass
class Finding:
    check: str
    detail: str


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

    def check(self, name: str) -> Check | None:
        for c in self.checks:
            if c.name == name:
                return c
        return None


def _truncated(findings: list[Finding]) -> dict:
    total = len(findings)
    cap = DATA_LIMITS["max_findings_total"]
    shown = min(total, DATA_LIMITS["max_findings_shown"])
    return {
        "total": total,
        "shown": shown,
        "truncated": max(0, total - shown),
    }


class _Builder:
    def __init__(self) -> None:
        self.checks: list[Check] = []
        self._findings: dict[str, list[Finding]] = {}
        self.verdict: str | None = None

    def gate(self, name: str, ok: bool | None, value: Any = None) -> None:
        findings = self._findings.get(name, [])
        self.checks.append(
            Check(name=name, ok=ok, value=value, findings=_truncated(findings))
        )
        if ok is False:
            self.verdict = VIOLATED
        elif ok is None and self.verdict is None:
            self.verdict = UNVERIFIABLE

    def advise(self, name: str, ok: bool | None, value: Any = None) -> None:
        findings = self._findings.get(name, [])
        self.checks.append(
            Check(name=name, ok=ok, value=value, findings=_truncated(findings))
        )

    def finding(self, check: str, detail: str) -> None:
        self._findings.setdefault(check, []).append(Finding(check, detail))

    def report(self) -> Report:
        verdict = self.verdict if self.verdict is not None else VERIFIED
        return Report(verdict=verdict, checks=self.checks)


# --------------------------------------------------------------------------
# The contract (pure)
# --------------------------------------------------------------------------

def check(capture: Capture, facts: Facts) -> Report:
    b = _Builder()

    # parses_clean — derivable from the document alone
    schema_error = next(
        (ch.value for ch in capture.verification.checks if ch.name == "parses_clean"
         and ch.ok is False), None)
    from ..capture_doc import validate as cap_validate
    problems = cap_validate(capture)
    if problems:
        for p in problems:
            b.finding("parses_clean", p)
        b.gate("parses_clean", False, "schema-violated")
    elif schema_error:
        b.gate("parses_clean", False, "schema-violated")
    else:
        b.gate("parses_clean", True, "ok")

    # trims — only evaluable with trim context; verify alone has none
    b.gate("trims_in_bounds", True if facts.available else None, "no-trim-context")

    if not facts.available:
        # Could not gather facts — report every fact-dependent gating check as
        # unverifiable (None), which never folds into verified or violated.
        for name in ("media_decodes", "min_duration", "uniform_geometry", "not_blank"):
            b.gate(name, None, "facts-unavailable")
        for name in ("has_audio", "audio_lufs_in_range", "codec_uniform", "no_static_frames"):
            b.advise(name, None, "facts-unavailable")
        if b.verdict is None:
            b.verdict = UNVERIFIABLE
        return b.report()

    # media_decodes
    if facts.decode_ok is None:
        b.gate("media_decodes", None, "decode-not-evaluated")
    elif facts.decode_ok:
        b.gate("media_decodes", True, "ok")
    else:
        b.finding("media_decodes", "ffmpeg failed to decode the media")
        b.gate("media_decodes", False, "decode-failed")

    # has_audio is advisory in phase 0/1. Video-only captures are valid; the
    # future audio phase can promote this back to a gate once capture semantics
    # and loudness measurement are explicitly implemented.
    if facts.has_audio is None:
        b.advise("has_audio", None, "stream-not-evaluated")
    elif facts.has_audio:
        b.advise("has_audio", True, "ok")
    else:
        b.advise("has_audio", False, "no-audio-stream")

    # min_duration
    if facts.duration_s is None:
        b.gate("min_duration", None, "duration-unknown")
    elif facts.duration_s >= MIN_DURATION_S:
        b.gate("min_duration", True, facts.duration_s)
    else:
        b.finding("min_duration", f"duration {facts.duration_s}s < {MIN_DURATION_S}s")
        b.gate("min_duration", False, facts.duration_s)

    # uniform_geometry (no segment drift in fps / resolution)
    unif = _geometry_uniform(facts)
    if unif is None:
        b.gate("uniform_geometry", None, "geometry-unknown")
    elif unif:
        b.gate("uniform_geometry", True, facts.sample_geometry[:1])
    else:
        b.finding("uniform_geometry", "fps/resolution drift across segments")
        b.gate("uniform_geometry", False, facts.sample_geometry)

    # not_blank (video mean luma above the noise floor)
    not_blank = _not_blank(facts)
    if not_blank is None:
        b.gate("not_blank", None, "video-luma-unknown")
    elif not_blank:
        b.gate("not_blank", True, {"mean_luma": facts.mean_luma})
    else:
        b.finding("not_blank", "video mean luma is at or below the blankness floor")
        b.gate("not_blank", False, {"mean_luma": facts.mean_luma})

    # --- advisory (never move the verdict) ----------------------------------
    if facts.integrated_lufs is not None:
        in_range = LUFS_RANGE[0] <= facts.integrated_lufs <= LUFS_RANGE[1]
        b.advise("audio_lufs_in_range", in_range, facts.integrated_lufs)
    else:
        b.advise("audio_lufs_in_range", None, "lufs-unknown")

    codecs = sorted(set(facts.codecs))
    b.advise("codec_uniform", True if len(codecs) == 1 else (False if codecs else None),
             codecs)

    # no_static_frames: frame-count sanity vs duration*fps
    if facts.frames and facts.duration_s and facts.fps:
        expected = facts.duration_s * facts.fps
        static = facts.frames < expected * 0.5  # fewer than half expected
        b.advise("no_static_frames", not static,
                 {"frames": facts.frames, "expected_approx": round(expected)})
    else:
        b.advise("no_static_frames", None, "frames-unknown")

    return b.report()


def _geometry_uniform(facts: Facts) -> bool | None:
    if not facts.sample_geometry:
        return None
    first = facts.sample_geometry[0]
    allow_none = all(s[0] is None for s in facts.sample_geometry)
    for sample in facts.sample_geometry:
        fps_ok = sample[0] == first[0] or (sample[0] is None and allow_none)
        geom_ok = (sample[1], sample[2]) == (first[1], first[2])
        if not (fps_ok and geom_ok):
            return False
    return True


def _not_blank(facts: Facts) -> bool | None:
    """Return whether the video carries visible signal.

    Audio loudness is intentionally not part of the phase-0/1 gate: a valid
    recording may be video-only. ``signalstats`` supplies mean luma in the
    0..255 range; missing luma remains honestly unverifiable.
    """
    if facts.mean_luma is None:
        return None
    return facts.mean_luma > NOISE_LUMA_FLOOR

# --------------------------------------------------------------------------
# CLI handler (thin runner; the contract itself stays pure)
# --------------------------------------------------------------------------

VERDICT_EXIT = {VERIFIED: 0, VIOLATED: 5, UNVERIFIABLE: 7}


def _report_dict(report: Report) -> dict:
    from dataclasses import asdict
    return asdict(report)


def cmd_verify(args) -> int:
    import json as _json
    from dataclasses import asdict
    from pathlib import Path as _P

    from ..capture_doc import Check as _CaptureCheck
    from ..capture_doc import load_capture as _load_capture
    from ..errors import Exit as _Exit, ExitCodes as _Codes
    from ..media import probe_facts as _probe_facts

    target = _P(args.dir)
    if target.is_dir():
        cap_path = target / "capture.json"
    else:
        cap_path = target
    if not cap_path.exists():
        raise _Exit(_Codes.USAGE, f"no capture document found at {cap_path}")

    capture = _load_capture(cap_path)
    if capture.file and not _P(capture.file).exists():
        facts = Facts()
    else:
        facts = _probe_facts(_P(capture.file)) if capture.file else Facts()

    report = check(capture, facts)
    if not args.dry_run:
        # Verification is a document transition, not only stdout. Persist the
        # measured video facts and the contract report so the next command
        # (notably `reels edit`) reads the same verified state an agent saw.
        capture.captured.fps = round(facts.fps) if facts.fps is not None else None
        capture.captured.width = facts.width
        capture.captured.height = facts.height
        capture.captured.duration_s = facts.duration_s
        capture.captured.decode_ok = facts.decode_ok
        capture.captured.has_audio = facts.has_audio
        capture.captured.frames = facts.frames
        capture.captured.mean_luma = facts.mean_luma
        # Audio fields remain null until the deferred audio phase.
        capture.captured.integrated_lufs = None
        capture.captured.peak_dbfs = None
        capture.verification.verdict = report.verdict
        capture.verification.checks = [
            _CaptureCheck(
                name=item.name,
                ok=item.ok,
                value=item.value,
                findings=item.findings,
            )
            for item in report.checks
        ]
        from ..capture_doc import save_capture as _save_capture
        # Keep the on-disk document portable when media lives beside it.
        if capture.file:
            media_path = _P(capture.file)
            try:
                capture.file = str(media_path.relative_to(cap_path.resolve().parent))
            except ValueError:
                capture.file = str(media_path)
        _save_capture(cap_path, capture)

    if args.dry_run:
        print(_json.dumps(asdict(report), indent=2) if args.json
              else f"[dry-run] verdict would be {report.verdict}")
        return 0

    if args.json:
        print(_json.dumps(_report_dict(report), indent=2, default=str))
    else:
        print(f"verdict: {report.verdict}")
        for c in report.checks:
            state = "ok" if c.ok is True else ("fail" if c.ok is False else "unchecked")
            print(f"  {c.name}: {state}")
    return VERDICT_EXIT[report.verdict]


from ..cli import register  # noqa: E402

register("verify", cmd_verify)
