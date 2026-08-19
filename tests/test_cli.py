"""Smoke tests for the CLI skeleton and shared plumbing (Unit 01)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reels import __version__
from reels.cli import main
from reels.errors import Exit, ExitCodes
from reels.identify import content_id


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_id_outputs_reel_hex(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello")
    assert content_id(f).startswith("reel-")
    assert len(content_id(f)) == 5 + 8  # reel- + 8 hex


def test_id_deterministic(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello")
    assert content_id(f) == content_id(f)


def test_id_different_content_differs(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("one")
    b.write_text("two")
    assert content_id(a) != content_id(b)


def test_list_json_inventory(tmp_path, capsys):
    (tmp_path / "capture.json").write_text(
        json.dumps({"schema_version": 1, "capture_id": "rec-abc", "captured": {}})
    )
    assert main(["list", "--json", str(tmp_path)]) == ExitCodes.OK
    inv = json.loads(capsys.readouterr().out)
    assert inv["captures"][0]["capture_id"] == "rec-abc"


def test_unknown_command_exits_2(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["bogus"])
    assert exc.value.code == ExitCodes.USAGE


def test_stub_commands_exit_70():
    # verify/prove/render are still stubs until Units 04/06/07
    for cmd in (["verify", "."], ["prove", "x.json"], ["render", "x.json"]):
        assert main(cmd) == ExitCodes.NOT_IMPLEMENTED, cmd


def test_exit_exception_carries_code():
    e = Exit(ExitCodes.MISSING_BINARY, "no ffmpeg")
    assert e.code == ExitCodes.MISSING_BINARY
    assert e.message == "no ffmpeg"
