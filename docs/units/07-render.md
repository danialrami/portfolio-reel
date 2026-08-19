# Unit 07 — Renderer: `reels render`

## Objective
Implement a pure-ffmpeg headless renderer that turns a `reel.json` into the final video — trims,
concat, fades, `drawtext` overlays, and intro/outro — with `--dry-run`, `--json`, and no
MoviePy/ImageMagick. Background music/ducking is deferred from phases 0/1.

## Context
- `docs/SPEC.md` — render command, output block, cross-platform ffmpeg-only stance.
- `docs/units/05-reel-document.md` (`Reel` schema this consumes), `docs/units/06-prove-metamorphic.md`
  (rendering is also what `deterministic` probes).
- Legacy bug to avoid: `create-reel.py` replaced clip audio with music; music must **duck under**
  (sidechaincompress) speech rather than replace it.

## Acceptance criteria
- [ ] `reels render reel.json --out out.mp4` produces a playable mp4, exits 0.
- [ ] Trims, fades, overlays, intro/outro, and an ordered concat are all applied via ffmpeg
      `filter_complex` only (no MoviePy import anywhere).
- [ ] Phase 0/1 does not capture or render audio; the existing `sidechaincompress` path is a
      deferred implementation to be re-enabled only with an audio contract and fixtures.
- [ ] `--dry-run --json` prints the exact ffmpeg command + filter graph and writes nothing, exit 0.
- [ ] Missing output dir / bad source exit per taxonomy (3/4), never a traceback.

## Interface contract
- `src/reels/render.py` → `build_filter_graph(reel: Reel, render_dir: Path) -> str` and
  `render(reel: Reel, out: Path, dry_run: bool) -> int`.
- Coexists with provenance: output is written to a temp dir then moved, so a failed render never
  leaves a half-written file at the destination.

## Boundaries — do NOT touch
- Do not validate relations (Unit 06) or author docs (Unit 05).
- Do not re-introduce obs-cli or OBS anywhere in the pipeline.

## Output
`src/reels/render.py`, `tests/test_render.py` (structural: filter graph correctness, crash-free).
Commit: `feat: ffmpeg renderer with music ducking`.

## Verification
```bash
uv run reels render --dry-run --json /tmp/reel.json
# live: capture 2 short shots, edit, render, then prove the result in Unit 06
```
