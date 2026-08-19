"""Unit 03: capture acquisition & platform adapters.

The test box is headless (no Wayland/X11), so live capture cannot run here;
we verify detection and command building by injecting env / which(), and the
dry-run path which emits no media. The live round-trip is validated in the
integration VM in Phase 5.
"""

from __future__ import annotations

import json
import sys

import pytest

from reels.adapters import CaptureRequest, detect
from reels.capture import run_capture
from reels.errors import Exit, ExitCodes


class FakeWhich:
    def __init__(self, present):
        self.present = set(present)

    def __call__(self, name):
        return name if name in self.present else None


def test_detect_x11_with_display():
    env = {"DISPLAY": ":0"}
    a = detect(env=env, which=FakeWhich([]))
    assert a.platform == "x11"
    assert a.tool == "ffmpeg:x11grab"


def test_detect_wayland_prefers_wl_screenrec():
    env = {"WAYLAND_DISPLAY": "wayland-0"}
    a = detect(env=env, which=FakeWhich(["wl-screenrec"]))
    assert a.platform == "wayland"
    assert a.tool == "wl-screenrec"


def test_detect_wayland_falls_back_to_wf_recorder():
    env = {"WAYLAND_DISPLAY": "wayland-0"}
    a = detect(env=env, which=FakeWhich(["wf-recorder"]))
    assert a.platform == "wayland"
    assert a.tool == "wf-recorder"


def test_detect_unsupported_raises_3(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "")
    monkeypatch.delenv("DISPLAY", raising=False)
    # force a non-darwin/win system by monkeypatching platform
    import reels.adapters as ad
    monkeypatch.setattr(ad.platform, "system", lambda: "Linux")
    with pytest.raises(Exit) as exc:
        detect(env={}, which=FakeWhich([]))
    assert exc.value.code == ExitCodes.SOURCE


def test_x11_command_uses_x11grab(monkeypatch, tmp_path):
    import reels.adapters as ad
    ad.detect = lambda env=None, which=None: ad.Adapter(
        "x11", "ffmpeg:x11grab", ad._build_x11
    )
    req = CaptureRequest(region="1920x1080+0+0", fps=30, out=str(tmp_path),
                         duration=3.0, name="demo")
    res = run_capture(req, dry_run=True)
    assert res.command[0] == "ffmpeg"
    assert "-f" in res.command and "x11grab" in res.command
    assert "-t" in res.command and "3.0" in res.command


def test_wayland_command_uses_monitor_flag(monkeypatch, tmp_path):
    import reels.adapters as ad
    ad.detect = lambda env=None, which=None: ad.Adapter(
        "wayland", "wl-screenrec", ad._build_wayland
    )
    req = CaptureRequest(region="monitor:0", fps=30, out=str(tmp_path), name="demo")
    res = run_capture(req, dry_run=True)
    assert res.command[0] == "wl-screenrec"
    assert "--monitor" in res.command
    assert "--audio" not in res.command


def test_dry_run_writes_no_media(monkeypatch, tmp_path):
    import reels.adapters as ad
    ad.detect = lambda env=None, which=None: ad.Adapter(
        "x11", "ffmpeg:x11grab", ad._build_x11
    )
    req = CaptureRequest(region="monitor:0", fps=30, out=str(tmp_path), name="demo")
    res = run_capture(req, dry_run=True)
    assert res.media_path is None
    assert not list((tmp_path).glob("*.mp4"))
    assert not (tmp_path / "capture.json").exists()


def test_bad_region_exits_3(monkeypatch, tmp_path):
    import reels.adapters as ad
    ad.detect = lambda env=None, which=None: ad.Adapter(
        "x11", "ffmpeg:x11grab", ad._build_x11
    )
    req = CaptureRequest(region="garbage", out=str(tmp_path), name="demo")
    with pytest.raises(Exit) as exc:
        run_capture(req, dry_run=True)
    assert exc.value.code == ExitCodes.SOURCE
