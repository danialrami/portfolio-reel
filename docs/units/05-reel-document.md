# Unit 05 — Reel Document & `reels edit`

## Objective
Define the normalized `reel.json` Editing Document and a headless `reels edit` that authors one
from verified recordings — ordering, trims, overlay text, and intro/outro. Music remains an empty,
explicitly deferred extension in phases 0/1.

## Context
- `docs/SPEC.md` — the Reel Document shape (output, style, intro/outro, music, clips[]).
- `docs/units/02-capture-document.md` (schema discipline) and `docs/units/04-verify-gating.md`
  (only verified captures should be editable).
- `docs/SPEC.md` and the legacy `config.yaml` fields (font, intro/outro text, music volume) which
  migrate into `reel.json`'s `style`/`intro`/`outro`/`music`.

## Acceptance criteria
- [ ] `reels edit --add rec-… --order 1 --out reel.json` (or the documented JSON/DSL) writes a
      schema-valid `reel.json`, exits 0.
- [ ] Defaults (fps/codec/size/fade/overlay style) are made explicit, never implicit.
- [ ] Editing a capture with `verification.verdict != "verified"` is refused with a warning + exit 5.
- [ ] `reels edit --dry-run --json` prints the would-be `reel.json` without writing.
- [ ] `parse_reel`/`to_json` round-trip cleanly (same discipline as Unit 02).

## Interface contract
- `src/reels/reel_doc.py` → `class Reel` (+ `parse_reel(text)`, `load_reel(path)`,
  `save_reel(path, r)`, `validate(r) -> list[str]`).
- `src/reels/edit.py` → `author(clips: list[ClipRef], opts) -> Reel` (sorts by `order`, resolves
  `capture_ref`, applies trims/overlays, attaches intro/outro; audio/music fields stay at their
  deferred defaults).
- `ClipRef = { capture_ref, trim_in, trim_out, order, overlay: {text, position} }`.

## Boundaries — do NOT touch
- Do not validate assembly relations (Unit 06) or render (Unit 07).
- Keep the Editing Document aligned with `schemas/reel/reel-v1.json`; parser and schema changes ship together.

## Output
`src/reels/reel_doc.py`, `src/reels/edit.py`, `tests/test_reel_doc.py`. Commit:
`feat: reel document and edit authoring`.

## Verification
```bash
uv run pytest tests/test_reel_doc.py -q
uv run reels edit --dry-run --json --out /tmp/reel.json
```
