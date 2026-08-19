# Unit 01 — Primitive scaffold & CLI skeleton

## Objective
Stand up the `reels` uv-managed Python package with the command dispatcher, shared `--json` /
exit-code plumbing, `list` inventory, and `id` identity — so every later unit hangs off a stable
shape and has a place to live.

## Context
- `docs/SPEC.md` — the command surface, exit-code taxonomy, design rules.
- Existing broken scripts `capture-portfolio-clip.py`, `create-reel.py`, `run-capture.sh` will be
  **replaced** by this package over later units; this unit only creates the skeleton.
- KB pattern: `agent-knowledge/docs/product/lufs-sfz/02-the-instrument-primitive.md`.

## Acceptance criteria
- [ ] `uv sync && uv run reels --version` prints a version and exits 0.
- [ ] `uv run reels list --json <root>` prints an inventory of captures/reels as JSON, exits 0.
- [ ] `uv run reels id <path>` prints `reel-<sha256 first 8>` for a file and exits 0.
- [ ] Unknown command prints usage to stderr and exits 2.
- [ ] `--json` is accepted on every registered command; `--dry-run` accepted where defined.

## Interface contract
- Package layout: `pyproject.toml` (name `reels`, `[project.scripts] reels = "reels.cli:main"`),
  `src/reels/__init__.py`, `src/reels/cli.py`, `src/reels/errors.py`, `src/reels/identify.py`.
- `reels/errors.py` exposes `EXIT = {...}` constants matching the SPEC taxonomy (0,2,3,4,5,6,7,70)
  and an `Exit(Exception)` carrying a code.
- Command registration: each subcommand is a function `cmd_<name>(args) -> int` reachable from
  `cli.main`; unimplemented subcommands return `70` (not-implemented sentinel).
- `reels/identify.py` exposes `content_id(path: Path) -> str` (returns `reel-<hex>`).

## Boundaries — do NOT touch
- Do not implement capture/verify/prove/render bodies (later units). Stub them as exit 70.
- Do not edit `docs/units/` other units' files.
- Do not create `capture.json`/`reel.json` schema files (Units 02/05).

## Output
Files added under `src/reels/` + `pyproject.toml` + `.python-version` (3.12). Commit style:
`feat: scaffold reels CLI skeleton`.

## Verification
```bash
uv sync
uv run reels --version && uv run reels list --json . && uv run reels id README.md
uv run reels bogus ; echo "exit=$?  # expect 2"
```
