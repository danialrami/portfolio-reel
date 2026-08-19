"""Unit 02: Capture Document schema & parser."""

from __future__ import annotations

import json

import pytest

from reels.capture_doc import (
    UNVERIFIABLE,
    VIOLATED,
    VERIFIED,
    Capture,
    Check,
    Requested,
    Source,
    Verification,
    load_capture,
    parse_capture,
    save_capture,
    to_json,
    validate,
)


def test_parse_fills_defaults():
    c = parse_capture(json.dumps({"capture_id": "rec-abc", "file": "clip.mp4"}))
    assert c.schema_version == 1
    assert c.capture_id == "rec-abc"
    # explicit defaults, never partial state
    assert c.requested.fps == 30
    assert c.requested.codec == "h264"
    assert c.requested.audio is False
    assert c.requested.mic is False
    assert c.requested.out == "./shots"
    # fresh, unverified doc is unverifiable, not "fine"
    assert c.verification.verdict == UNVERIFIABLE
    assert [ch for ch in c.verification.checks if ch.name == "parses_clean"][0].ok is True
    assert c.captured.fps is None
    assert c.capture_id == "rec-abc"


def test_parse_full_document():
    doc = {
        "schema_version": 1,
        "capture_id": "rec-12345678",
        "source": {"platform": "wayland", "tool": "wl-screenrec", "region": "monitor:0"},
        "requested": {"fps": 30, "codec": "h264", "audio": False, "mic": False, "out": "./shots"},
        "captured": {
            "fps": 30, "width": 1920, "height": 1080, "duration_s": 12.4,
            "decode_ok": True, "has_audio": False, "frames": 372,
            "mean_luma": 128.0, "integrated_lufs": None, "peak_dbfs": None,
        },
        "file": "20260619_153000_label.mp4",
    }
    c = parse_capture(json.dumps(doc))
    assert c.source.platform == "wayland"
    assert c.captured.width == 1920
    assert c.captured.mean_luma == 128.0
    assert c.captured.integrated_lufs is None
    assert c.captured.frames == 372
    assert c.file == "20260619_153000_label.mp4"
    assert validate(c) == []


def test_malformed_json_is_violated_not_crash():
    c = parse_capture("{not json")
    assert c.verification.verdict == VIOLATED
    names = [ch.name for ch in c.verification.checks]
    assert "parses_clean" in names
    assert not [ch for ch in c.verification.checks if ch.name == "parses_clean"][0].ok


def test_unknown_schema_version_is_violated():
    c = parse_capture(json.dumps({"schema_version": 99, "capture_id": "rec-x"}))
    assert c.verification.verdict == VIOLATED
    assert not [ch for ch in c.verification.checks if ch.name == "parses_clean"][0].ok


def test_non_dict_is_violated():
    c = parse_capture(json.dumps([1, 2, 3]))
    assert c.verification.verdict == VIOLATED


def test_roundtrip():
    doc = {
        "capture_id": "rec-1111",
        "source": {"platform": "mac", "tool": "ffmpeg:avfoundation", "region": "monitor:0"},
        "requested": {"fps": 60, "audio": True},
        "captured": {"fps": 60, "width": 1920, "height": 1080, "decode_ok": True},
        "file": "clip.mp4",
        "verification": {"verdict": VERIFIED, "checks": [{"name": "media_decodes", "ok": True}]},
    }
    c = parse_capture(json.dumps(doc))
    assert parse_capture(to_json(c)) == c


def test_validate_reports_structural_problems():
    c = parse_capture(json.dumps({"schema_version": 1}))
    problems = validate(c)
    assert any("capture_id" in p for p in problems)
    assert any("file" in p for p in problems)


def test_load_resolves_file_relative_to_doc_dir(tmp_path):
    src = tmp_path / "media" / "clip.mp4"
    src.parent.mkdir()
    src.write_bytes(b"x")
    doc = tmp_path / "capture.json"
    doc.write_text(json.dumps({"capture_id": "rec-a", "file": "media/clip.mp4"}))
    c = load_capture(doc)
    assert c.file == str(src.resolve())


def test_save_roundtrips(tmp_path):
    c = parse_capture(json.dumps({"capture_id": "rec-save", "file": "m.mp4"}))
    p = tmp_path / "capture.json"
    save_capture(p, c)
    assert parse_capture(p.read_text()) == c
