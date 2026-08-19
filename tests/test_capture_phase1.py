"""Phase 0/1 capture behavior: video-only and portable output paths."""

from __future__ import annotations

import json
import sys

import pytest

from reels import adapters as ad
from reels.adapters import CaptureRequest
from reels.capture import run_capture
from reels.errors import Exit, ExitCodes


def test_audio_capture_is_honest_not_implemented(tmp_path):
    with pytest.raises(Exit) as exc:
        run_capture(CaptureRequest(out=str(tmp_path), audio=True), dry_run=True)
    assert exc.value.code == ExitCodes.NOT_IMPLEMENTED


def test_capture_writes_media_under_out_and_document(monkeypatch, tmp_path):
    code = "from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(b'fake-video')"

    def build(_req):
        return [sys.executable, "-c", code, "capture.mp4"]

    monkeypatch.setattr(
        ad,
        "detect",
        lambda env=None, which=None: ad.Adapter("x11", "fake", build),
    )
    result = run_capture(
        CaptureRequest(out=str(tmp_path), name="path-check", duration=0.1),
        dry_run=False,
    )

    assert result.media_path == tmp_path / "capture.mp4"
    assert result.media_path.exists()
    document = json.loads((tmp_path / "capture.json").read_text())
    assert document["file"] == "capture.mp4"
    assert document["content_sha256"]


def test_capture_without_output_is_source_failure(monkeypatch, tmp_path):
    def build(_req):
        return [sys.executable, "-c", "pass", "missing.mp4"]

    monkeypatch.setattr(
        ad,
        "detect",
        lambda env=None, which=None: ad.Adapter("x11", "fake", build),
    )
    with pytest.raises(Exit) as exc:
        run_capture(CaptureRequest(out=str(tmp_path), duration=0.1), dry_run=False)
    assert exc.value.code == ExitCodes.SOURCE
    assert not (tmp_path / "capture.json").exists()
