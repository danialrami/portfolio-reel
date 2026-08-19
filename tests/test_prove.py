"""Unit 06: metamorphic contract (reels prove) — three verdicts."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from reels.contracts.prove import AssemblyFacts, check, cmd_prove
from reels.errors import ExitCodes
from reels.reel_doc import Reel, ClipRef, IntroOutro, Music, Overlay, save_reel
from reels.edit import author

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe required",
)


def _reel(trim_in=0.2, trim_out=1.8):
    clips = [
        ClipRef(capture_ref="rec-one", order=1, trim_in=trim_in, trim_out=trim_out,
                overlay=Overlay(text="Title", position="bottom-left")),
        ClipRef(capture_ref="rec-two", order=2, trim_in=trim_in, trim_out=trim_out),
    ]
    return author(clips, intro=IntroOutro(text="INTRO", duration=1.0),
                  outro=IntroOutro(text="OUTRO", duration=1.0),
                  music=Music(file="", volume=0.15, duck_under_speech=True))


def _good_facts():
    return AssemblyFacts(
        available=True,
        total_duration=5.2,
        clip_durations=[1.6, 1.6],
        intro_duration=1.0,
        outro_duration=1.0,
        output_fps=30.0,
        output_width=1920, output_height=1080,
        geometry_uniform=True,
        output_has_audio=False,
        clips_have_audio=False,
        overlay_boxes=[{"x": 20, "y": 0, "w": 300, "h": 60}],
        music_present=False,
        music_duck_on=True,
        first_is_intro=True,
        last_is_outro=True,
        deterministic_stable=True,
    )


# --- three verdicts (pure) --------------------------------------------------

def test_verified_when_all_relations_hold():
    r = check(_reel(), _good_facts())
    assert r.verdict == "verified"
    for name in ("durations_sum", "concat_continuous", "fps_constant",
                 "overlay_fits", "audio_end_to_end", "music_ducked",
                 "dimensions_match", "intro_outro_ordered", "deterministic"):
        assert r.check(name).ok is True, name


def test_violated_when_durations_do_not_sum():
    facts = _good_facts()
    facts.total_duration = 9.0  # way off expected ~5.2
    r = check(_reel(), facts)
    assert r.verdict == "violated"
    assert r.check("durations_sum").ok is False
    assert r.check("concat_continuous").ok is False


def test_violated_when_fps_drifts():
    facts = _good_facts()
    facts.output_fps = 15.0
    r = check(_reel(), facts)
    assert r.verdict == "violated"
    assert r.check("fps_constant").ok is False


def test_violated_when_overlay_overflows():
    facts = _good_facts()
    facts.overlay_boxes = [{"x": 20, "y": 1000, "w": 3000, "h": 800}]
    r = check(_reel(), facts)
    assert r.verdict == "violated"
    assert r.check("overlay_fits").ok is False


def test_violated_when_intro_outro_out_of_order():
    facts = _good_facts()
    facts.first_is_intro = False
    r = check(_reel(), facts)
    assert r.verdict == "violated"
    assert r.check("intro_outro_ordered").ok is False


def test_unverifiable_when_facts_unavailable():
    r = check(_reel(), AssemblyFacts(available=False))
    assert r.verdict == "unverifiable"
    for name in ("durations_sum", "fps_constant", "deterministic"):
        assert r.check(name).ok is None, name


def test_deterministic_skipped_is_unverifiable_when_renders_skipped():
    facts = _good_facts()
    facts.deterministic_stable = None
    r = check(_reel(), facts)
    assert r.check("deterministic").ok is None


# --- real round-trip: build media, edit, prove ------------------------------

def _clip(path: Path, seconds: float) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         "color=c=blue:s=320x240:r=30:d=%s" % seconds,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        capture_output=True, check=False,
    )
    return path


def _make_capture(tmp_path, cid, media):
    from reels.capture_doc import Capture, save_capture
    save_capture(tmp_path / f"{cid}.capture.json", Capture(capture_id=cid, file=str(media)))


def test_prove_real_assembly(tmp_path):
    c1 = _clip(tmp_path / "c1.mp4", 2.0)
    c2 = _clip(tmp_path / "c2.mp4", 2.0)
    _make_capture(tmp_path, "rec-one", c1)
    _make_capture(tmp_path, "rec-two", c2)

    reel = author(
        [ClipRef(capture_ref="rec-one", order=1, trim_in=0.2, trim_out=1.8),
         ClipRef(capture_ref="rec-two", order=2, trim_in=0.2, trim_out=1.8)],
        intro=IntroOutro(text="", duration=0.0),
        outro=IntroOutro(text="", duration=0.0),
        music=Music(file="", volume=0.15, duck_under_speech=True),
    )
    reel_path = tmp_path / "reel.json"
    save_reel(reel_path, reel)

    class Args:
        reel = str(reel_path)
        captures = str(tmp_path)
        json = False
        dry_run = False

    assert cmd_prove(Args()) == ExitCodes.OK


def test_prove_dry_run_returns_0_no_render(tmp_path):
    reel_path = tmp_path / "reel.json"
    save_reel(reel_path, _reel())

    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        class Args:
            reel = str(reel_path)
            captures = "."
            json = True
            dry_run = True
        rc = cmd_prove(Args())
    assert rc == ExitCodes.OK
    payload = json.loads(buf.getvalue())
    assert payload["dry_run"] is True
