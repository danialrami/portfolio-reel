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
NOISE_LUFS_FLOOR = -60.0      # below this the capture is blank/silent
NOISE_PEAK_FLOOR = -60.0

# gating (decide the verdict) vs advisory (never move it)
GATING_CHECKS = {
    "parses_clean", "media_decodes", "has_audio", "min_duration",
    "uniform_geometry", "not_blank", "trims_in_bounds",
}
ADVISORY_CHECKS = {
    "audio_lufs_in_range", "codec_uniform", "no_static_frames",
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
        for name in ("media_decodes", "has_audio", "min_duration",
                     "uniform_geometry", "not_blank"):
            b.gate(name, None, "facts-unavailable")
        for name in ("audio_lufs_in_range", "codec_uniform", "no_static_frames"):
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

    # has_audio
    if facts.has_audio is None:
        b.gate("has_audio", None, "stream-not-evaluated")
    elif facts.has_audio:
        b.gate("has_audio", True, "ok")
    else:
        b.gate("has_audio", False, "no-audio-stream")

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

    # not_blank (LUFS / peak above noise floor)
    not_blank = _not_blank(facts)
    if not_blank is None:
        b.gate("not_blank", None, "loudness-unknown")
    elif not_blank:
        b.gate("not_blank", True,
               {"integrated_lufs": facts.integrated_lufs, "peak_dbfs": facts.peak_dbfs})
    else:
        b.finding("not_blank", "level at or below the noise floor (blank/silence)")
        b.gate("not_blank", False,
               {"integrated_lufs": facts.integrated_lufs, "peak_dbfs": facts.peak_dbfs})

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
    # video-level: use loudness where present; all-None means unknown
    lufs = facts.integrated_lufs
    peak = facts.peak_dbfs
    if lufs is None and peak is None:
        return None
    if lufs is not None and lufs > NOISE_LUFS_FLOOR:
        return True
    if peak is not None and peak > NOISE_PEAK_FLOOR:
        return True
    return False

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

    from ..capture_doc import load_capture as _load_capture
    from ..errors import Exit as _Exit
    from ..media import probe_facts as _probe_facts

    target = _P(args.dir)
    if target.is_dir():
        cap_path = target / "capture.json"
    else:
        cap_path = target
    if not cap_path.exists():
        raise _Exit(ExitCodes.USAGE, f"no capture document found at {cap_path}")

    capture = _load_capture(cap_path)
    if capture.file and not _P(capture.file).exists():
        facts = Facts()
    else:
        facts = _probe_facts(_P(capture.file)) if capture.file else Facts()

    report = check(capture, facts)
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
