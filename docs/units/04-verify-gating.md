# Unit 04 — Contract one: `reels verify` (gating)

## Objective
Implement the pure gating contract over a `Capture` — three verdicts, declared truncation, and
the shared ffprobe/media-facts runner. An agent can prove a take is whole before using it.

## Context
- `docs/SPEC.md` — Contract one table, the three-verdict doctrine.
- `docs/units/02-capture-document.md`, `docs/units/03-capture-acquisition.md`.
- KB: the "proven, not exited 0" posture and `unverifiable` in
  `agent-knowledge/docs/product/lufs-sfz/02-the-instrument-primitive.md`.

## Acceptance criteria
- [ ] `reels verify <dir> --json` returns `verified` (exit 0) for a clean capture.
- [ ] Returning `violated` (exit 5) for a capture under min duration / blank video
      (mean luma ≤ noise floor) / with invalid structure. Missing audio is advisory in phases 0/1.
- [ ] Returns `unverifiable` (exit 7) when facts cannot be gathered (e.g. media missing, no
      ffprobe) — **never** folds "couldn't check" into verified or violated.
- [ ] Each check carries `findings { total, shown, truncated }`; finding lists are capped by
      `DATA_LIMITS`.
- [ ] The contract body performs no IO: all facts (decode, geometry, mean luma, duration) are
      passed in from a thin runner. Audio presence/LUFS/peak remain deferred advisory fields.

## Interface contract
- `src/reels/contracts/verify.py` → `check(capture: Capture, facts: Facts) -> Report` where
  `Report = { verdict: 'verified'|'violated'|'unverifiable', checks: list[Check] }` and `Check =
  { name, ok: bool|null, value?, findings: {total,shown,truncated} }`.
- `src/reels/media.py` → `probe_facts(path: Path) -> Facts` (runs `ffprobe` and `signalstats`
  for video geometry/mean luma; audio LUFS/peak measurement is deferred; raises `Exit(4)` or
  returns a not-available sentinel for unverifiable).
- `reels verify` persists the measured facts and report back into `capture.json`, then sets the
  process exit per the taxonomy (0/5/7).

## Boundaries — do NOT touch
- Do not implement the assembly contract (Unit 06) or renderer (Unit 07).
- `src/reels/media.py` is shared — define it here; later units only *read* it.

## Output
`src/reels/contracts/verify.py`, `src/reels/media.py`, `tests/test_verify.py` covering all three
verdicts. Commit: `feat: gating contract reels verify`.

## Verification
```bash
uv sync && uv run pytest tests/test_verify.py -q
uv run reels capture --dry-run --json ; uv run reels verify /tmp/shots --json ; echo "exit=$?"
```
