# AGENTS.md — `reels`

## Mission

`reels` is a contract-first, headless video-process primitive. It turns recordings into portable JSON documents and turns verified recordings into editing plans. The goal is not a browser editor or a universal creative-workflow protocol: the documents and contracts are the product; CLI, PWA, and future Workchain components are consumers.

## Current scope

Phases 0 and 1 are **video-only**:

- recording: `reels capture` writes media plus `capture.json`;
- verification: `reels verify` gathers ffprobe/ffmpeg video facts, evaluates the recording contract, and persists the report back into `capture.json`;
- editing: `reels edit` accepts only recordings whose persisted verdict is `verified` and writes `reel.json`;
- proof/render: `reels prove` checks assembly relations and `reels render` renders video with ffmpeg.

Audio capture, microphone capture, LUFS/peak measurement, and background-music ducking are deferred. Audio-shaped fields remain in the document shapes as future extension points, but phase-0/1 commands must not silently capture or claim to verify audio.

## Source of truth

- Recording document schema: `schemas/capture/capture-v1.json`
- Editing document schema: `schemas/reel/reel-v1.json`
- Recording parser/serializer: `src/reels/capture_doc.py`
- Editing parser/serializer: `src/reels/reel_doc.py`
- Recording contract: `src/reels/contracts/verify.py`
- Editing/assembly contract: `src/reels/contracts/prove.py`
- Media facts runner: `src/reels/media.py`
- Command dispatcher: `src/reels/cli.py`
- Phase boundary: `docs/PHASES.md`
- Full specification: `docs/SPEC.md`

The JSON Schemas describe normalized written artifacts. The Python parsers are intentionally tolerant at input boundaries. Cross-field rules that Draft 7 cannot express, such as `trim_out >= trim_in`, remain Python validation rules.

## Safe agent workflow

1. Read the relevant parser, contract, schema, and tests before changing behavior.
2. Work on a branch; never push directly to `main`.
3. Keep changes small and document the contract change in the same PR.
4. Use `--json` for machine consumption and inspect the declared verdict, not only the process exit code.
5. Treat `verified` as earned only when every gating check is `true`; `unverifiable` is not success.
6. Run the focused tests, then `PATH=/agent/.local/bin:$PATH uv run pytest -q` (or the equivalent local `uv run pytest -q`) before calling a change complete.
7. Do not add audio behavior to a video-only phase. Add a contract, platform source definition, fixtures, and an explicit phase change before promoting audio from advisory/deferred to gating.

## Command contract

```text
reels capture [--out DIR] [--name LABEL] [--region REGION] [--fps FPS]
              [--duration SECONDS] [--codec CODEC] [--dry-run] [--json]
reels verify DIR_OR_CAPTURE_JSON [--dry-run] [--json]
reels edit [--add CAPTURE_ID]... [--order N] [--trim-in S] [--trim-out S]
           [--overlay-text TEXT] [--captures DIR] [--out FILE] [--dry-run] [--json]
reels prove REEL_JSON [--captures DIR] [--dry-run] [--json]
reels render REEL_JSON [--captures DIR] [--out FILE] [--dry-run] [--json]
reels list [ROOT] [--json]
reels id PATH [--json]
```

Exit codes are part of the public contract: 0 success, 2 usage, 3 source unavailable, 4 required binary missing, 5 contract violated, 6 interrupted, 7 unverifiable, 70 not implemented/deferred.

## Extension seams

- New recording sources belong in `src/reels/adapters/` and must emit the same Recording Document. Window, terminal/PTY, browser, webcam, and monitor-specific sources are adapters, not new schemas.
- New editing operations belong in the Editing Document and renderer contract, with a schema change, parser tests, a metamorphic relation where possible, and a fixture.
- New checks belong in the pure contract module and receive facts from the thin media/renderer runner. Never put subprocess or filesystem IO inside a contract.
- Keep content identity deterministic and preserve relative media paths when saving documents.
