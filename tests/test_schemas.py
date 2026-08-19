"""Phase 1: recording/editing JSON Schema contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator


ROOT = Path(__file__).parents[1]


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


@pytest.mark.parametrize(
    "schema_path",
    [
        ROOT / "schemas/capture/capture-v1.json",
        ROOT / "schemas/reel/reel-v1.json",
    ],
)
def test_schema_is_valid_draft7(schema_path: Path) -> None:
    schema = _load(schema_path)
    Draft7Validator.check_schema(schema)


def test_capture_example_matches_recording_schema() -> None:
    schema = _load(ROOT / "schemas/capture/capture-v1.json")
    instance = _load(ROOT / "examples/capture.json")
    errors = sorted(Draft7Validator(schema).iter_errors(instance), key=str)
    assert errors == []


def test_reel_examples_match_editing_schema() -> None:
    schema = _load(ROOT / "schemas/reel/reel-v1.json")
    validator = Draft7Validator(schema)
    for path in (ROOT / "examples/reel.json", ROOT / "reel.json"):
        errors = sorted(validator.iter_errors(_load(path)), key=str)
        assert errors == [], f"{path}: {errors}"


def test_capture_schema_preserves_tri_state_and_audio_defer() -> None:
    schema = _load(ROOT / "schemas/capture/capture-v1.json")
    instance = _load(ROOT / "examples/capture.json")
    instance["verification"]["checks"] = [
        {
            "name": "media_decodes",
            "ok": None,
            "value": "facts-unavailable",
            "findings": {"total": 0, "shown": 0, "truncated": 0},
        },
        {
            "name": "not_blank",
            "ok": True,
            "value": {"mean_luma": 128.0},
            "findings": {"total": 0, "shown": 0, "truncated": 0},
        },
    ]
    assert list(Draft7Validator(schema).iter_errors(instance)) == []

    instance["requested"]["audio"] = True
    assert list(Draft7Validator(schema).iter_errors(instance))


def test_reel_schema_rejects_audio_inputs_in_phase_one() -> None:
    schema = _load(ROOT / "schemas/reel/reel-v1.json")
    instance = _load(ROOT / "examples/reel.json")
    instance["music"]["file"] = "assets/music.mp3"
    assert list(Draft7Validator(schema).iter_errors(instance))
