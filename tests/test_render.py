"""Unit 07: renderer structural checks + a real synthetic end-to-end render."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from reels.capture_doc import Capture, save_capture
from reels.edit import author
from reels.errors import Exit
from reels.reel_doc import ClipRef, IntroOutro, Music, Overlay, save_reel, load_reel
from reels.render import (
    build_filter_graph,
    render,
    resolve_clip_media,
)

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe required",
)


def _clip(path: Path, seconds: float, tone: int = 440) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         "color=c=blue:s=320x240:r=30:d=%s" % seconds,
         "-f", "lavfi", "-i", "sine=frequency=%s:duration=%s" % (tone, seconds),
         "-shortest", "-c:v", "libx264", "-c:a", "aac", str(path)],
        capture_output=True, check=False,
    )
    return path


def _music(path: Path) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=8",
         "-c:a", "aac", str(path)],
        capture_output=True, check=False,
    )
    return path

def _make_capture_doc(tmp_path: Path, cid: str, media: Path) -> None:
    c = Capture(capture_id=cid, file=str(media))
    save_capture(tmp_path / f"{cid}.capture.json", c)


@pytest.fixture
def fx(tmp_path):
    class FX:
        root = tmp_path
        clip1 = _clip(tmp_path / "clip1.mp4", 2.0, 440)
        clip2 = _clip(tmp_path / "clip2.mp4", 2.0, 660)
        music = _music(tmp_path / "bg.m4a")

    _make_capture_doc(tmp_path, "rec-one", FX.clip1)
    _make_capture_doc(tmp_path, "rec-two", FX.clip2)
    return FX


def _make_reel(fx, music=True) -> Path:
    clips = [
        ClipRef(capture_ref="rec-one", order=1, trim_in=0.2, trim_out=1.8,
                overlay=Overlay(text="Title\\nRole", position="bottom-left")),
        ClipRef(capture_ref="rec-two", order=2, trim_in=0.2, trim_out=1.8),
    ]
    r = author(
        clips,
        intro=IntroOutro(text="INTRO", duration=1.0),
        outro=IntroOutro(text="OUTRO", duration=1.0),
        music=Music(file=str(fx.music) if music else "", volume=0.15,
                    duck_under_speech=True),
    )
    out = fx.root / "reel.json"
    save_reel(out, r)
    return out


def test_build_filter_graph_contains_expected(fx):
    reel_path = _make_reel(fx)
    reel = load_reel(reel_path)
    media = resolve_clip_media(reel_path, reel, fx.root)
    dur = [c.trim_out - c.trim_in for c in reel.clips]
    g = build_filter_graph(reel, media, dur, [True, True], fx.music, True)
    assert "concat=n=" in g
    assert "drawtext=" in g
    assert "sidechaincompress" in g
    assert "fade=t=" in g


def test_dry_run_writes_nothing_and_shows_graph(fx):
    reel_path = _make_reel(fx)
    out = fx.root / "out.mp4"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = render(reel_path, out, dry_run=True, captures_root=fx.root)
    assert rc == 0
    assert not out.exists()
    payload = json.loads(buf.getvalue())
    assert payload["filter_complex"]
    assert payload["ffmpeg"][0] == "ffmpeg"


def test_real_render_produces_playable_mp4(fx):
    reel_path = _make_reel(fx)
    out = fx.root / "out.mp4"
    assert render(reel_path, out, dry_run=False, captures_root=fx.root) == 0
    assert out.exists() and out.stat().st_size > 0
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,format_name",
         "-of", "csv=p=0", str(out)],
        capture_output=True, text=True,
    )
    assert probe.returncode == 0
    assert probe.stdout.strip()  # decodable


def test_render_missing_source_exits_3(fx):
    reel_path = _make_reel(fx)
    fx.clip1.unlink()
    with pytest.raises(Exit) as exc:
        render(reel_path, fx.root / "nope.mp4", dry_run=False,
               captures_root=fx.root)
    assert exc.value.code == 3
