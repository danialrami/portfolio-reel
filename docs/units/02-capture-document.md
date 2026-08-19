# Unit 02 — Capture Document schema & parser

## Objective
Define the normalized `capture.json` Recording Document and a single load/save/validate module —
the seed of the recording flow (one schema, many consumers). The written artifact is specified by
`schemas/capture/capture-v1.json`.

## Context
- `docs/SPEC.md` — the Capture Document shape (`schema_version`, `capture_id`, `source`,
  `requested`, `captured`, `file`, `content_sha256`, `verification`).
- `docs/units/01-scaffold-and-cli.md` — the package layout this hangs off.
- KB pattern: Instrument Document in `02-the-instrument-primitive.md` (provenance, explicit
  defaults, normalised paths).

## Acceptance criteria
- [ ] `parse_capture(json_text) -> Capture` parses valid JSON into a typed object; every missing
      default is filled explicitly (schema_version, verdict fields) with no partial state.
- [ ] Paths are normalised and `file` is resolved relative to the document's directory.
- [ ] Malformed JSON / unknown schema_version produces a `parses_clean=false` verdict, not a crash.
- [ ] `to_json(Capture) -> str` round-trips `parse_capture(to_json(c)) == c`.

## Interface contract
`src/reels/capture_doc.py` exposes:
- `class Capture` (dataclass) with fields matching the schema;
- `parse_capture(text: str) -> Capture`;
- `load_capture(path: Path) -> Capture` (reads + normalises paths);
- `save_capture(path: Path, c: Capture) -> None`;
- `VALIDATE` sentinel or `validate(c) -> list[str]` (list of schema violations, empty if clean).

## Boundaries — do NOT touch
- Do not compute media facts (that is Unit 04 / `reels/media.py`).
- Do not implement `capture` acquisition (Unit 03) or `verify` (Unit 04).
- Do not define `reel.json` (Unit 05).

## Output
`src/reels/capture_doc.py` + a unit-test file `tests/test_capture_doc.py` wrapping the acceptance
criteria. Commit: `feat: capture document schema and parser`.

## Verification
```bash
uv run pytest tests/test_capture_doc.py -q
```
