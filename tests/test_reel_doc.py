"""Unit 05: Reel Document & reels edit."""

from __future__ import annotations

import json

import pytest

from reels.capture_doc import UNVERIFIABLE, VERIFIED, VIOLATED, Capture
from reels.edit import author, cmd_edit, find_capture
from reels.errors import Exit
from reels.reel_doc import (
    ClipRef,
    Overlay,
    Reel,
    load_reel,
    parse_reel,
    save_reel,
    to_json,
    validate,
)
from reels.identify import content_id


def make_capture(capture_id, verdict=VERIFIED):
    return parse_doc(capture_id, verdict)


def parse_doc(cid, verdict):
    c = Capture(capture_id=cid, file="clip.mp4")
    c.verification.verdict = verdict
    return c


def test_author_sorts_by_order_and_defaults_explicit():
    r = author(
        [
            ClipRef(capture_ref="rec-b", order=2, trim_in=10, trim_out=40),
            ClipRef(capture_ref="rec-a", order=1),
        ]
    )
    assert [c.capture_ref for c in r.clips] == ["rec-a", "rec-b"]
    # explicit defaults
    assert r.output.fps == 30
    assert r.output.size == "1920x1080"
    assert r.output.video_codec == "libx264"
    assert r.output.audio_codec == "aac"
    assert r.style.fade_duration == 0.5
    assert r.style.overlay_bg == "rgba(0,0,0,0.5)"
    assert r.music.volume == 0.15
    assert r.music.duck_under_speech is True
    assert validate(r) == []


def test_roundtrip():
    r = author([ClipRef(capture_ref="rec-x", order=1)])
    assert r.reel_id  # reel_id assigned
    assert r.reel_id.startswith("reel-")
    assert parse_reel(to_json(r)) == r


def test_reel_id_deterministic():
    r1 = author([ClipRef(capture_ref="rec-x", order=1)])
    r2 = author([ClipRef(capture_ref="rec-x", order=1)])
    assert r1.reel_id == r2.reel_id


def test_reel_id_changes_with_clips():
    r1 = author([ClipRef(capture_ref="rec-x", order=1)])
    r2 = author([ClipRef(capture_ref="rec-y", order=1)])
    assert r1.reel_id != r2.reel_id


def test_malformed_reel_is_violated_not_crash():
    r = parse_reel("{nope")
    assert r.verification.verdict == VIOLATED
    assert not [c for c in r.verification.checks if c.name == "parses_clean"][0].ok


def test_validate_reports_trim_out_less_than_in():
    r = author([ClipRef(capture_ref="rec-a", order=1, trim_in=40, trim_out=10)])
    assert any("trim_out < trim_in" in p for p in validate(r))


def test_save_assigns_reel_id(tmp_path):
    r = author([ClipRef(capture_ref="rec-a", order=1)])
    p = tmp_path / "reel.json"
    save_reel(p, r)
    assert r.reel_id
    assert parse_reel(p.read_text()) == r


def test_find_capture_matches_by_id(tmp_path):
    doc = tmp_path / "capture.json"
    c = make_capture("rec-find")
    c.file = str((tmp_path / "clip.mp4"))
    save_capture(doc, c)
    found = find_capture(tmp_path, "rec-find")
    assert found is not None
    assert found.capture_id == "rec-find"


def test_find_capture_missing(tmp_path):
    assert find_capture(tmp_path, "rec-nope") is None


def test_edit_refuses_unverified_capture(tmp_path):
    doc = tmp_path / "capture.json"
    c = make_capture("rec-unver", verdict=UNVERIFIABLE)
    c.file = "clip.mp4"
    save_capture(doc, c)

    class Args:
        add = ["rec-unver"]
        order = 1
        trim_in = None
        trim_out = None
        overlay_text = None
        captures = str(tmp_path)
        out = str(tmp_path / "reel.json")
        dry_run = False
        json = False

    with pytest.raises(Exit) as exc:
        cmd_edit(Args())
    assert exc.value.code == 5


def test_edit_dry_run_writes_nothing(tmp_path):
    doc = tmp_path / "capture.json"
    c = make_capture("rec-ok")
    c.file = "clip.mp4"
    save_capture(doc, c)

    class Args:
        add = ["rec-ok"]
        order = 1
        trim_in = None
        trim_out = None
        overlay_text = None
        captures = str(tmp_path)
        out = str(tmp_path / "reel.json")
        dry_run = True
        json = True

    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cmd_edit(Args())
    assert rc == 0
    assert not (tmp_path / "reel.json").exists()
    payload = json.loads(buf.getvalue())
    assert payload["clips"][0]["capture_ref"] == "rec-ok"


def test_edit_writes_reel_json(tmp_path):
    doc = tmp_path / "capture.json"
    c = make_capture("rec-write")
    c.file = "clip.mp4"
    save_capture(doc, c)

    class Args:
        add = ["rec-write"]
        order = 1
        trim_in = None
        trim_out = None
        overlay_text = "Title"
        captures = str(tmp_path)
        out = str(tmp_path / "reel.json")
        dry_run = False
        json = False

    assert cmd_edit(Args()) == 0
    r = load_reel(tmp_path / "reel.json")
    assert r.clips[0].capture_ref == "rec-write"
    assert r.clips[0].overlay.text == "Title"


# small local helper to save a capture doc
from reels.capture_doc import save_capture  # noqa: E402
