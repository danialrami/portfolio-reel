---
name: reels
version: 0.1.0
status: phase-0-1-video-only
---

# Reels agent skill

Use this skill when an agent needs to record a screen, verify a recording, author an editing plan, prove an assembly, render a video reel, or inspect the recording/editing registry.

## Contract-first behavior

- Read `schemas/capture/capture-v1.json` for the recording flow and `schemas/reel/reel-v1.json` for the editing flow.
- Use the `reels` console command, not ad-hoc ffmpeg graphs, when creating or verifying project artifacts.
- Use `--json` whenever output is consumed by an agent.
- After `reels verify`, read the persisted `capture.json`; the report is part of the artifact and is what `reels edit` trusts.
- Never treat an exit code alone as proof. `verified` means all gating checks passed; `unverifiable` means the agent could not evaluate a required fact.

## Recording flow

```bash
uv run reels capture --out ./shots --name demo --region monitor:0 --duration 3 --json
uv run reels verify ./shots --json
```

Phase 0/1 recording is video-only. The CLI does not expose `--audio` or `--mic`. The verifier uses ffprobe plus video `signalstats` mean luma for the blankness gate. Audio presence is advisory and LUFS/peak fields remain deferred. Programmatic requests for audio return the honest not-implemented exit code 70 rather than silently capturing it.

## Editing flow

Only a persisted recording with `verification.verdict == "verified"` may be edited:

```bash
uv run reels edit --add rec-0123abcd --order 1 --captures ./shots --out reel.json --json
uv run reels prove reel.json --captures ./shots --json
uv run reels render reel.json --captures ./shots --out Reel.mp4 --json
```

Keep `music.file` empty in phase 0/1. Intro/outro, trims, overlays, deterministic identity, and video rendering are in scope. The preliminary audio graph is dormant and must not be described as current support.

## Extension work

Add a new capture source as an adapter that writes the same Recording Document. Add a new editing operation by changing the Editing Document schema, parser, renderer, metamorphic proof, and fixtures together. Window/terminal/PTY/browser/webcam capture are future adapters, not reasons to fork the document formats.
