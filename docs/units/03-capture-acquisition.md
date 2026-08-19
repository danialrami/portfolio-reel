# Unit 03 — Capture acquisition & platform adapter

## Objective
Implement headless `reels capture`: detect the platform, drive ffmpeg (or `wl-screenrec` /
`wf-recorder` on wlroots Wayland), write media + a `capture.json`, with `--dry-run`, `--json`,
and clean signal handling. No interactive prompts.

## Context
- `docs/SPEC.md` — capture command surface + the per-platform adapter table; no obs-cli.
- `docs/units/02-capture-document.md` — `capture_doc` module used to write the manifest.
- Platform research (2026): Linux X11 `ffmpeg -f x11grab`; Linux wlroots/Hyprland
  `wl-screenrec`/`wf-recorder`; macOS `ffmpeg -f avfoundation`; Windows `ffmpeg -f gdigrab`/`ddagrab`.

## Acceptance criteria
- [ ] `reels capture --dry-run --json` (no capture) reports the detected platform + adapter and the
      exact command it would run, emits no media, exits 0.
- [ ] `reels capture --region monitor:0` records N seconds (honoring `--duration` or a SIGINT/`--name`
      stop) and writes: media file **and** a `capture.json` referencing it, and `--json` emits the
      document. Exits 0.
- [ ] On a X11 session the chosen command is `ffmpeg -f x11grab …`; on a detected wlroots Wayland
      session it is `wl-screenrec`/`wf-recorder`; on unsupported, exits 3 with `unverifiable`.
- [ ] Aborting capture (SIGINT) leaves a partial file and a `capture.json` with `verification.verdict =
      "unverifiable"` and exits 6, per taxonomy.

## Interface contract
- `src/reels/capture.py` → `run_capture(req: CaptureRequest, dry_run: bool) -> Capture`; writes the
  media and returns a `Capture` (schema version 1) that later units can verify.
- `src/reels/adapters/__init__.py` → `detect() -> Adapter` and each adapter provides
  `build_command(req) -> list[str]` and `probe_sources() -> list[dict]`.
- `CaptureRequest` is a small dataclass: `region | monitor | window`, `fps`, `audio`, `mic`,
  `duration | None`, `codec`, `out`, `name`.

## Boundaries — do NOT touch
- Do not compute integrated LUFS or decode checks (Unit 04 / `reels/media.py`).
- Do not author `reel.json` (Unit 05).

## Output
`src/reels/capture.py`, `src/reels/adapters/*`, `tests/test_capture.py`. Commit:
`feat: headless capture with platform adapters`.

## Verification
```bash
uv run reels capture --dry-run --json --out /tmp/shots
# live (headless): record ~3s of a monitor, then prove it verifies in Unit 04
```
