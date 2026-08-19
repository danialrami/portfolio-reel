# Unit 08 — Docs, example reel, migration note

## Objective
Make the `reels` primitive self-documenting and the repo's README accurate: rewrite `README.md`,
ship an example `reel.json`, and note the migration from the legacy OBS/MoviePy scripts.

## Context
- `docs/SPEC.md` — everything to document (commands, documents, contracts, taxonomy).
- The current `README.md` describes the broken `capture-portfolio-clip.py` / `create-reel.py`
  OBS/MoviePy workflow; it must be replaced, not amended in place.
- Obsidian/Kando integration notes in the old README should be preserved in spirit (a one-shot to
  kick off `reels capture`).

## Acceptance criteria
- [ ] `README.md` documents install (`uv sync`), every `reels` subcommand, both documents, both
      contracts, the exit-code table, and an end-to-end video-only "capture → verify → edit → prove → render"
      quickstart.
- [ ] `examples/capture.json` and `examples/reel.json` validate against the separate recording/editing
      schemas and the CLI can `prove`/`render --dry-run` the editing example.
- [ ] A `docs/PHASES.md` states that audio is deferred and maps the future extension points.
- [ ] A `docs/legacy-migration.md` (or README section) maps old `config.yaml` fields to
      `reel.json` and states obs-cli/OBS + MoviePy are no longer required.
- [ ] Historical references to the old scripts are clearly marked as migration context, not current commands.

## Interface contract
None (docs only). Must point at the exact command names and schema from `docs/SPEC.md` and
`docs/units/*.md` — do not introduce new names.

## Boundaries — do NOT touch
- No code changes. Do not edit `pyproject.toml` or `src/` (other units own those).

## Output
`README.md` (rewritten), `examples/reel.json`, `docs/legacy-migration.md`. Commit:
`docs: document reels primitive and migration`.

## Verification
```bash
uv run reels prove --dry-run examples/reel.json   # exit 0 once Units 06/07 exist
grep -rn "create-reel\|capture-portfolio-clip" README.md docs/ | wc -l   # historical context may remain in migration/spec pages
```
