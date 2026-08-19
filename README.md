# reels — a screen-capture & reel primitive

`reels` is a LUFS-family primitive for turning day-to-day work into portfolio
reels. It ships two *documents* — a **Capture Document** (`capture.json`) and a
**Reel Document** (`reel.json`) — plus two *contracts* over them
(`reels verify`, `reels prove`), so an agent can capture, assemble, and prove
a reel **headlessly** with explicit exit codes and never a silent "exit 0 but
wrong".

The primitive is the two documents plus the two contracts. Every consumer (a
CLI today, a PWA/editor later) reads the documents and never re-implements them.
The only runtime dependency shared everywhere is **ffmpeg** (+ `ffprobe`) —
no OBS, no obs-cli, no MoviePy.

## Install

```bash
uv sync            # Python >=3.12, uv-managed
uv run reels --version
```

## Command surface

```
reels <command> [options] [--json]
  capture   Record a screen/window shot        -> media + capture.json
  verify    Contract one against a capture     (is the capture whole?)
  edit      Author a reel.json from captures   (order, trims, overlays, intro/outro/music)
  prove     Contract two against an assembly   (did it behave as asked?)
  render    ffmpeg render a reel.json          -> output file
  list      Inventory captures/reels under a root
  id        Deterministic content identity     (reel-<hex>)
```

Design rules: strong defaults, `--json` on every command, `--dry-run` for
pre-flight, NDJSON progress on capture/render, and a documented exit-code
taxonomy. No interactive prompts.

### Exit-code taxonomy

| Code | Meaning |
|---|---|
| 0 | success (captured+verified / proved / rendered) |
| 2 | usage / bad args |
| 3 | capture source (region/device) unavailable |
| 4 | required binary missing (ffmpeg / ffprobe / capture tool) |
| 5 | contract **violated** |
| 6 | interrupted before a valid output |
| 7 | contract **unverifiable** (not failed — couldn't evaluate) |
| 70 | not implemented (honest-failure sentinel) |

## The two documents

### Capture Document — `capture.json` (one per recorded shot)

Normalised, typed, machine-readable statement of what a capture *is*:
provenance (`source.platform/tool/region`), what was *requested* (`fps`,
`codec`, `audio`, `mic`), what was *captured* (geometry, duration, frames,
integrated LUFS / peak dBFS), the media `file` and its `content_sha256`, and a
`verification` block (verdict + checks).

### Reel Document — `reel.json` (the timeline / assembly manifest)

The output block, `style`, `intro`/`outro`, `music`, and an ordered list of
trimmed `clips` with optional overlays — each `capture_ref` pointing at a
verified capture. See [`examples/reel.json`](examples/reel.json).

## The two contracts — three verdicts

Both contracts are **pure functions of their inputs** (no IO in the contract
body; a thin runner gathers facts). Each gating check is tri-state, and the
third state is the point:

```
verified      all gating checks passed            -> exit 0
violated      at least one gating check failed    -> exit 5
unverifiable  a gating check could not be evaluated -> exit 7
```

Two-state tools fold "I couldn't check" into one of the others and lie.
`reels` reports it honestly. Every check carries declared truncation
(`findings { total, shown, truncated }`).

### Contract one — `reels verify` (is the capture whole?)

Gating: `parses_clean`, `media_decodes`, `has_audio`, `min_duration`,
`uniform_geometry`, `not_blank`, `trims_in_bounds`.

Advisory (never move the verdict): `audio_lufs_in_range`, `codec_uniform`,
`no_static_frames`.

### Contract two — `reels prove` (did the assembly behave as asked?)

Metamorphic — no golden output to diff, so it asserts *relations*: 
`durations_sum`, `concat_continuous`, `fps_constant`, `overlay_fits`,
`audio_end_to_end`, `music_ducked`, `dimensions_match`,
`intro_outro_ordered`, `deterministic` (same `reel.json` + inputs ⇒
byte-identical render).

## End-to-end quickstart

```bash
# 1. capture a shot (headless; SIGINT stops it, leaving a partial + unverifiable doc)
reels capture --out ./shots --name demo --region monitor:0 --audio --json

# 2. prove the take is whole before using it
reels verify ./shots --json            # exit 0 (verified)

# 3. author a reel from verified captures
reels edit --add rec-……06 --order 1 --add rec-……2a --order 2 \
      --captures ./shots --out reel.json

# 4. prove the assembly behaves as asked (re-renders for determinism)
reels prove reel.json --captures ./shots --json      # exit 0 (verified)

# 5. render the final video
reels render reel.json --captures ./shots --out PortfolioDemo.mp4
```

## Platforms

ffmpeg is the single cross-platform engine with thin per-platform capture
adapters:

| Platform | Adapter |
|---|---|
| Linux X11 | `ffmpeg -f x11grab` |
| Linux Wayland (wlroots / Hyprland / Omarchy) | `wl-screenrec` (preferred) or `wf-recorder` |
| macOS | `ffmpeg -f avfoundation` |
| Windows | `ffmpeg -f gdigrab` |

Rendering is a pure-ffmpeg `filter_complex` build — trims, fades, `drawtext`
overlays, intro/outro, ordered concat, and background-music **ducking**
(`sidechaincompress`) that never replaces clip audio.

## Repository layout

```
src/reels/
  cli.py            command dispatcher (--json / --dry-run / exit taxonomy)
  errors.py         exit-code taxonomy
  identify.py       deterministic content identity (reel-<hex>)
  capture_doc.py    Capture Document schema + parser
  reel_doc.py       Reel Document schema + parser
  adapters/         platform capture adapters (x11 / wayland / mac / win)
  capture.py        headless capture -> media + capture.json
  media.py          ffprobe/ffmpeg facts runner (LUFS, decode, geometry)
  contracts/
    verify.py       Contract one (gating) + verify CLI
    prove.py        Contract two (metamorphic) + prove CLI
  render.py         pure-ffmpeg renderer
tests/              per-unit test suites
docs/SPEC.md        the specification
docs/units/         unit-of-work contracts
docs/legacy-migration.md   old OBS/MoviePy -> reels mapping
examples/reel.json  sample reel document
```

## Spec & philosophy

- [`docs/SPEC.md`](docs/SPEC.md) — the full specification and command surface.
- [`docs/units/`](docs/units/) — unit-of-work contracts a fresh agent can build
  from with no other context.
- KB doctrine this replicates: one parser, two contracts, three verdicts,
  declared truncation, deterministic identity — "proven, not exited 0".
