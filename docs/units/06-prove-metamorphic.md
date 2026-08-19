# Unit 06 — Contract two: `reels prove` (metamorphic)

## Objective
Implement the metamorphic assembly contract over a `Reel` — relations that must hold for *any*
reel — with the same three-verdict and declared-truncation discipline as Unit 04. This is the
"satisfied the contract, not just exited 0" guarantee for the assembled output.

## Context
- `docs/SPEC.md` — Contract two table (`durations_sum`, `concat_continuous`, `fps_constant`,
  `overlay_fits`, `audio_end_to_end`, `music_ducked`, `dimensions_match`, `intro_outro_ordered`,
  `deterministic`).
- `docs/units/04-verify-gating.md` — same verdict/truncation machinery; reuse patterns and
  `reels/media.py` (read-only).
- KB: metamorphic contract rationale in `verifier-philosophy/04-metamorphic-value.md`.

## Acceptance criteria
- [ ] `reels prove reel.json --json` returns `verified` (exit 0) for a well-formed assembly.
- [ ] Detects and reports as `violated` (exit 5): clip durations not summing to total, a gap/jump
      at a boundary, non-uniform fps/size, an overlay overflowing the frame, intro/outro out of
      order.
- [ ] Returns `unverifiable` (exit 7) when facts are unavailable — never folds into verified/
      violated.
- [ ] `deterministic` check re-renders (or hashes) a small probe and asserts byte-identity for
      equal inputs + seed. (`--dry-run` skips the render.)
- [ ] Findings lists capped + `{total,shown,truncated}` declared.

## Interface contract
- `src/reels/contracts/prove.py` → `check(reel: Reel, facts: AssemblyFacts) -> Report` (same
  `Report`/`Check` shape as Unit 04).
- `src/reels/media.py` gains (or exposes) `probe_timeline(paths) -> AssemblyFacts`.

## Boundaries — do NOT touch
- Do not build the ffmpeg render graph (Unit 07). `deterministic` may call into a shared hash
  helper only.
- Do not edit `src/reels/contracts/verify.py` (Unit 04 owns it).

## Output
`src/reels/contracts/prove.py`, `tests/test_prove.py` covering all three verdicts. Commit:
`feat: metamorphic contract reels prove`.

## Verification
```bash
uv run pytest tests/test_prove.py -q
```
