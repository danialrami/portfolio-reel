"""Unit 04: gating contract (reels verify) — three verdicts."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from reels.capture_doc import Capture, Verification
from reels.contracts.verify import (
    LUFS_RANGE,
    MIN_DURATION_S,
    check,
    cmd_verify,
)
from reels.errors import ExitCodes
from reels.media import Facts, probe_facts

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe required for media fixture",
)


# --- fixtures ---------------------------------------------------------------

def _good_facts():
    return Facts(
        available=True,
        duration_s=12.4,
        width=1920, height=1080, fps=30.0, frames=372,
        decode_ok=True, has_audio=True,
        integrated_lufs=-18.2, peak_dbfs=-6.1,
        codecs=["h264", "aac"],
        sample_geometry=[(30.0, 1920, 1080)] * 3,
    )


def _capture():
    c = Capture(capture_id="rec-abc", file="clip.mp4")
    return c


def _make_clip(path: Path, *, seconds: float = 2.0, silent: bool = False) -> Path:
    src = "color=c=white:s=320x240:r=30:d=%s" % seconds
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", src, "-pix_fmt", "yuv420p",
           "-shortest", str(path)]
    if not silent:
        cmd = (["ffmpeg", "-y", "-f", "lavfi", "-i", src,
                "-f", "lavfi", "-i", "sine=frequency=440:duration=%s" % seconds,
                "-shortest", "-c:v", "libx264", "-c:a", "aac", str(path)])
    subprocess.run(cmd, capture_output=True, text=True, check=False)
    return path


# --- pure contract: three verdicts ------------------------------------------

def test_verified_when_all_gating_ok():
    r = check(_capture(), _good_facts())
    assert r.verdict == "verified"
    for name in ("parses_clean", "media_decodes", "has_audio", "min_duration",
                 "uniform_geometry", "not_blank", "trims_in_bounds"):
        assert r.check(name).ok is True, name


def test_violated_when_blank():
    facts = _good_facts()
    facts.integrated_lufs = -80.0
    facts.peak_dbfs = -80.0
    r = check(_capture(), facts)
    assert r.verdict == "violated"
    assert r.check("not_blank").ok is False


def test_violated_when_no_audio():
    facts = _good_facts()
    facts.has_audio = False
    r = check(_capture(), facts)
    assert r.verdict == "violated"
    assert r.check("has_audio").ok is False


def test_violated_when_under_min_duration():
    facts = _good_facts()
    facts.duration_s = 0.2
    r = check(_capture(), facts)
    assert r.verdict == "violated"
    assert r.check("min_duration").ok is False


def test_violated_when_decode_fails():
    facts = _good_facts()
    facts.decode_ok = False
    r = check(_capture(), facts)
    assert r.verdict == "violated"
    assert r.check("media_decodes").ok is False


def test_violated_when_geometry_drifts():
    facts = _good_facts()
    facts.sample_geometry = [(30.0, 1920, 1080), (15.0, 1920, 1080)]
    r = check(_capture(), facts)
    assert r.verdict == "violated"
    assert r.check("uniform_geometry").ok is False


def test_unverifiable_when_facts_missing():
    r = check(_capture(), Facts(available=False))
    assert r.verdict == "unverifiable"
    # never folds "couldn't check" into verified or violated
    for name in ("media_decodes", "has_audio", "min_duration", "not_blank"):
        assert r.check(name).ok is None, name


def test_findings_capped_and_declared():
    facts = _good_facts()
    # inject many parsings problems to force truncation on the finding list
    c = _capture()
    r = check(c, facts)
    assert r.check("min_duration").findings["truncated"] >= 0
    assert set(r.check("min_duration").findings) == {"total", "shown", "truncated"}


def test_parses_clean_false_violates():
    c = _capture()
    c.capture_id = ""  # schema violation
    r = check(c, _good_facts())
    assert r.verdict == "violated"
    assert r.check("parses_clean").ok is False


# --- media facts runner against real ffmpeg --------------------------------

def test_probe_facts_real_clip(tmp_path):
    clip = _make_clip(tmp_path / "clip.mp4", seconds=1.5, silent=False)
    facts = probe_facts(clip)
    assert facts.available is True
    assert facts.duration_s is not None and facts.duration_s >= 1.0
    assert facts.width == 320 and facts.height == 240
    assert facts.decode_ok is True
    assert facts.has_audio is True
    assert facts.integrated_lufs is not None and facts.integrated_lufs > -60


def test_probe_facts_missing_file_unverifiable(tmp_path):
    facts = probe_facts(tmp_path / "nope.mp4")
    assert facts.available is False


# --- CLI verify exit codes ---------------------------------------------------

def _write_capture(tmp_path, clip, verdict_relevant=True):
    c = _capture()
    c.capture_id = "rec-abc"
    c.file = str(clip)
    c.verification = Verification(verdict="unverifiable")
    from reels.capture_doc import save_capture
    save_capture(tmp_path / "capture.json", c)
    return tmp_path


def test_cmd_verify_verified(tmp_path, capsys):
    clip = _make_clip(tmp_path / "clip.mp4", seconds=1.5)
    _write_capture(tmp_path, clip)

    class Args:
        dir = str(tmp_path)
        json = False
        dry_run = False

    assert cmd_verify(Args()) == ExitCodes.OK


def test_cmd_verify_unverifiable_missing_media(tmp_path, capsys):
    d = tmp_path / "empty"
    d.mkdir()
    c = _capture()
    from reels.capture_doc import save_capture
    c.file = str(tmp_path / "missing.mp4")
    save_capture(d / "capture.json", c)

    class Args:
        dir = str(d)
        json = False
        dry_run = False

    import reels.contracts.verify as v
    # media missing -> facts unavailable -> unverifiable (exit 7)
    assert cmd_verify(Args()) == ExitCodes.UNVERIFIABLE


def test_cmd_verify_missing_doc_exits_usage_cleanly(tmp_path):
    """No capture.json -> clean usage exit (2), never a traceback."""
    from reels.contracts.verify import cmd_verify

    class Args:
        dir = str(tmp_path)
        json = False
        dry_run = False

    import pytest as _pt
    from reels.errors import Exit
    with _pt.raises(Exit) as exc:
        cmd_verify(Args())
    assert exc.value.code == ExitCodes.USAGE
