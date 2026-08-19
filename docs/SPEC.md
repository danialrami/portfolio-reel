# SPEC — `reels`: a LUFS-family screen-capture & reel primitive

**Status:** proposed · **Owner:** Daniel · **Companion KB suites:**
`agent-knowledge/docs/product/lufs-sfz/02-the-instrument-primitive.md`,
`agent-knowledge/docs/product/lufs-recorder/`, `.../verifier-philosophy/`

## The problem

`portfolio-reel` today is two ad-hoc scripts — an OBS-gated capture (`capture-portfolio-clip.py`)
and a MoviePy assembler (`create-reel.py`) — joined by loose hand-written YAML. It does not run
as committed (filename/reference mismatches, mixed MoviePy API generations), it cannot be driven
by an agent (interactive prompts, no `--json`, no exit-code taxonomy), and the parts that exist
do not agree with the KB's doctrine: nothing *verifies* a capture or an assembly, so "exit 0 but
wrong" slips through silently.

The goal is not to polish those scripts. It is to **reframe from players/glue to a primitive** —
the layer underneath the tooling that nobody else ships, exactly as `02-the-instrument-primitive.md`
reframes a sampler.

## The reframe

```
   capture (ffmpeg / wl-screenrec)          edit (timeline)
        │                                        │
        ▼                                        ▼
   Capture Document (capture.json)   ──▶   Reel Document (reel.json)
        │                                        │
        └──────── debug/verify ◀── prove ────────┘
                              │
                              ▼
                    ffmpeg render (reels render)
                              │
                              ▼
                         reel.mp4
```

A PWA and a CLI are consumers. **The primitive is the two documents plus the two contracts over
them**, and every consumer reads the documents and never re-implements them. One schema, several
consumers, so the interfaces cannot drift — the same one-parser discipline the KB applies to
`lib/workchain_yaml.py` and to `sfz-core`.

## Goals / constraints

1. **Agent-drivable.** Every command non-interactive: arguments, not prompts; `--json` on every
   command; `--dry-run`; a documented exit-code taxonomy; headless capture start/stop (no
   `input("Press Enter…")`).
2. **CLI-native capture, not a GUI adapter.** obs-cli is rejected: it wraps OBS (a heavy GUI app)
   rather than being a capture tool itself. **ffmpeg is the single cross-platform engine**, with
   thin per-platform capture adapters:
   - Linux X11 → `ffmpeg -f x11grab`
   - Linux Wayland (wlroots incl. Hyprland/Omarchy) → `wl-screenrec` (preferred, HW encode) or
     `wf-recorder`; both encode via ffmpeg. A portal/PipeWire path is the fallback.
   - macOS → `ffmpeg -f avfoundation`
   - Windows → `ffmpeg -f gdigrab` / `ddagrab`
3. **Cross-platform & maintainable.** Only runtime dependency shared everywhere is `ffmpeg`
   (+`ffprobe`). Capture adapters are thin, swappable, and platform-detected. Render is a pure
   ffmpeg `filter_complex` build — no MoviePy, no ImageMagick, no fragile API churn.
4. **Verified, not "exited 0".** Two contracts, each with **three verdicts**:
   `verified · violated · unverifiable`. "I could not check" is never reported as "fine".
5. **uv-managed Python.** `uv` for the project venv/lock. Python ≥3.12. Standard library for the
   CLI (`argparse`, `json`, `subprocess`); zero third-party Python deps for the core.

## The documents (the unit of value)

### Capture Document — `capture.json` (one per recorded shot)

Normalised, typed, machine-readable statement of what a capture *is*:

```jsonc
{
  "schema_version": 1,
  "capture_id": "rec-<8hex>",
  "created": "2026-...Z",
  "source": { "platform": "wayland|win|mac|x11", "tool": "wl-screenrec|ffmpeg:gdigrab|...", "region": "monitor:0|1920x1080+0+0|window:<id>" },
  "requested": { "fps": 30, "codec": "h264", "audio": true, "mic": false, "out": "./shots" },
  "captured": {
    "fps": 30, "width": 1920, "height": 1080, "duration_s": 12.4,
    "decode_ok": true, "has_audio": true, "frames": 372,
    "integrated_lufs": -18.2, "peak_dbfs": -6.1
  },
  "file": "20260619_153000_label.mp4",
  "content_sha256": "…", "reel_id": "reel-<hex>",
  "verification": { "verdict": "verified", "checks": [ { "name": "media_decodes", "ok": true } ] }
}
```

Every default made explicit; every path normalised; the media hash gives deterministic identity.

### Reel Document — `reel.json` (the timeline/assembly manifest)

```jsonc
{
  "schema_version": 1,
  "reel_id": "reel-<hex>",
  "output": { "filename": "ReelName.mp4", "fps": 30, "video_codec": "libx264", "audio_codec": "aac", "size": "1920x1080" },
  "style": { "font": "…", "overlay_bg": "rgba(0,0,0,0.5)", "fade_duration": 0.5 },
  "intro":  { "text": "NAME\n…", "duration": 5 },
  "outro":  { "text": "…", "duration": 7 },
  "music":  { "file": "assets/bg.mp3", "volume": 0.15, "duck_under_speech": true },
  "clips": [
    { "capture_ref": "rec-…", "trim_in": 10, "trim_out": 40, "order": 1,
      "overlay": { "text": "Title\nRole\nClient — Year", "position": "bottom-left" } }
  ],
  "verification": { "verdict": "verified", "checks": [] }
}
```

## Contract one — is the capture whole? (`reels verify`)

Pure function of `(capture_doc, facts)`; the caller supplies ffprobe/media facts, the contract
touches no IO so it runs identically in the CLI, a browser and a future workchain step.

**Gating (decide the verdict):**

| Check | The question |
|---|---|
| `parses_clean` | is the `capture.json` schema-valid |
| `media_decodes` | does ffprobe open the media, stream readable |
| `has_audio` | is there an audio stream with measurable level |
| `min_duration` | is duration ≥ threshold (no 0.2s dead capture) |
| `uniform_geometry` | is fps/resolution stable (no segment drift) |
| `not_blank` | is mean brightness / LUFS above noise floor (not all-black/silence) |
| `trims_in_bounds` | do `trim_in`/`trim_out` fall inside the capture |

**Advisory** (never move the verdict): `audio_lufs_in_range`, `codec_uniform`, `no_static_frames`.

## Contract two — did the assembly behave as asked? (`reels prove`)

Metamorphic, because a reel has no golden output to diff against — assert *relations* that must
hold for any reel whatsoever:

| Check | The relation |
|---|---|
| `durations_sum` | total ≈ sum of trimmed clips + intro + outro |
| `concat_continuous` | no gap/jump at clip boundaries (time continuity) |
| `fps_constant` | output frame rate constant across the reel |
| `overlay_fits` | every overlay box falls inside the frame |
| `audio_end_to_end` | every second has audio except declared-muted regions |
| `music_ducked` | where music + speech co-occur, music is quieter (sanity, not taste) |
| `dimensions_match` | all source geometry uniform or explicitly scaled |
| `intro_outro_ordered` | intro first, outro last |
| `deterministic` | same `reel.json` + inputs ⇒ byte-identical render |

## Three verdicts — and the third is the point

```
verified      all gating checks passed
violated      at least one gating check failed
unverifiable  a gating check could not be evaluated
```

Two-state tools fold "I couldn't check" into one of the others and lie. The `unverifiable`
verdict — plus **declared truncation** (each check carries `findings { total, shown, truncated }`,
caps in `DATA_LIMITS`) — is the whole posture, per `verifier-philosophy`.

## Command surface

```
reels <command> [options] [--json]
  capture      Record a screen/window shot → media + capture.json.
                 --out <dir> --name <label> --region <WxH+X+Y|monitor:N|window>
                 --fps --audio --mic --duration --codec --dry-run
  verify <dir>      Contract one against an existing capture.
  edit              Author a Reel Document from captures (or a small JSON/DSL).
  prove <reel.json> Contract two against an assembly.
  render <reel.json> ffmpeg render → output file. --out --dry-run
  list              Inventory captures/reels under a root.
  id <path>         Deterministic content identity (reel-<hex>).
```

Design rules: strong defaults, `--json` on every command, NDJSON progress on capture/render,
`--dry-run` for pre-flight, `verify`/`prove`/`render` all exit per the taxonomy.

## Exit-code taxonomy

| Code | Meaning |
|---|---|
| 0 | success (captured+verified / proved / rendered) |
| 2 | usage / bad args |
| 3 | capture source (region/device) unavailable |
| 4 | required binary missing (ffmpeg / ffprobe / capture tool) |
| 5 | contract **violated** |
| 6 | interrupted before a valid output |
| 7 | contract **unverifiable** (not failed — couldn't evaluate) |
| 70 | not implemented (honest-failure sentinel for stubbed commands) |

## Boundaries — what this is NOT

- **Not** an autosampler or audio DAW. Audio capture is pass-through for the demo; no editing of
  audio beyond music ducking.
- **Not** obs-cli / OBS. No GUI adapter is the source of truth.
- **Not** a browser player. A PWA/editor is a *consumer* of the documents, built later, never the
  product.
- **Not** taste. No check judges whether a reel is good — only whether it is whole and behaved
  as asked.

## Done-criteria (whole project)

- `reels capture / verify / edit / prove / render / list / id` all work headless, emit `--json`,
  honor the exit taxonomy, and `verify`/`prove` return three distinct verdicts.
- A demo capture+edit+render round-trip is verified end to end on this Omarchy/Hyprland box.
- The docs + units in `docs/` let a fresh agent rebuild the entire thing with no other context.

## Related

- KB `lufs-sfz/02-the-instrument-primitive.md` — the pattern this replicates (one parser, two
  contracts, three verdicts, declared truncation, deterministic id).
- KB `lufs-recorder/` — the audio capture sibling; `take.json` already computes integrated LUFS.
- KB `verifier-philosophy/` — the "proven, not exited 0" doctrine.
