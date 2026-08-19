# Delivery phases

`reels` is being delivered as two related, contract-first flows rather than as a universal media platform all at once.

## Phase 0 — verified recording baseline

Phase 0 makes a screen recording a portable, honest artifact:

- `reels capture` produces video-only media and a `capture.json` Recording Document.
- `reels verify` probes the media, evaluates the video gates, persists the measured facts and the tri-state report back into `capture.json`, and returns 0/5/7 for verified/violated/unverifiable.
- Output paths are resolved under `--out`; a failed capture cannot masquerade as a completed document.
- The package can be installed as a wheel, including `reels.adapters` and `reels.contracts`.

The current capture adapters are screen/monitor-oriented. Window selection, terminal/PTY capture, browser capture, and webcam capture are later adapters. They should write the same Recording Document rather than introduce new document formats.

## Phase 1 — verified editing baseline

Phase 1 makes an editing plan a portable, inspectable artifact:

- `reels edit` consumes verified Recording Documents and writes a `reel.json` Editing Document.
- `reels prove` and `reels render` operate on that document without a browser or GUI being the source of truth.
- `schemas/capture/capture-v1.json` is the recording-flow schema.
- `schemas/reel/reel-v1.json` is the editing-flow schema.
- `AGENTS.md`, `llms.txt`, and `.agents/skills/reels.md` are the agent-discovery surface.

The schemas describe normalized written documents. Python parsers remain responsible for tolerant input handling and cross-field rules such as `trim_out >= trim_in`, which Draft 7 JSON Schema cannot express.

## Audio boundary

Audio is intentionally out of scope for phases 0 and 1. The CLI does not expose audio or microphone capture, Wayland does not add audio implicitly, video verification uses signalstats mean luma for `not_blank`, and `has_audio`/LUFS/peak fields remain advisory or null extension points.

The renderer and contract modules still contain the preliminary audio graph and audio-shaped fields because the future audio phase will need a stable place to attach. Those paths are dormant in the video-only flow; do not describe them as current audio support. The follow-up phase must define platform audio sources, capture semantics, loudness measurement, and their own verification fixtures before audio is promoted into a gate.
