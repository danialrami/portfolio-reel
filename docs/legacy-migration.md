# Legacy migration: OBS/MoviePy → `reels`

The original `portfolio-reel` was two ad-hoc scripts — an OBS-gated capture
(`capture_portfolio_clip.py`) and a MoviePy assembler (`create_reel.py`) —
joined by hand-written YAML and driven by interactive prompts and `obs-cli`.
That stack did not run as committed (filename/reference mismatches, mixed
MoviePy API generations), could not be driven headlessly by an agent, and
verified nothing.

`reels` **replaces** those scripts. The legacy files
`capture_portfolio_clip.py`, `create_reel.py`, and `run_capture.sh` are
removed. **obs-cli, OBS, and MoviePy are no longer required anywhere in the
pipeline.** The only runtime dependency shared across platforms is `ffmpeg`
(+ `ffprobe`).

## Migration map: `config.yaml` → `reel.json`

The legacy per-reel `config.yaml` fields move into the Reel Document
(`reel.json`). Everything below is now explicit, never implicit.

| Legacy `config.yaml`          | `reel.json` field                                  |
|-------------------------------|----------------------------------------------------|
| `font`                        | `style.font`                                       |
| `fontsize` (overlay)          | fixed in the renderer's `drawtext` (42px)          |
| `text_color`                  | fixed white with border (renderer)                 |
| `text_bg_color`               | `style.overlay_bg`                                 |
| `fade_duration`               | `style.fade_duration`                              |
| `intro_text` / `intro_duration` | `intro.text` / `intro.duration`                  |
| `intro_fontsize` / `intro_bg_color` | fixed in the renderer                          |
| `outro_text` / `outro_duration` | `outro.text` / `outro.duration`                 |
| `background_music`            | `music.file`                                       |
| `background_volume`           | `music.volume`                                     |
| `output_filename`             | `output.filename`                                  |
| `fps` / `video_codec` / `audio_codec` | `output.fps` / `output.video_codec` / `output.audio_codec` |

### Per-clip metadata (legacy `N.yaml`)

| Legacy `N.yaml` | `reel.json` clip field          |
|-----------------|---------------------------------|
| `order`         | `clips[].order`                 |
| `start` / `end` | `clips[].trim_in` / `clips[].trim_out` |
| `title` / `role` / `client` / `year` | `clips[].overlay.text` (multi-line) |

### Black and white

| Legacy                              | `reels`                                                        |
|-------------------------------------|----------------------------------------------------------------|
| Interactive `input()` prompts       | headless args; `--json`/`--dry-run` on every command           |
| OBS + `obs-cli` recording           | `reels capture` via ffmpeg / `wl-screenrec` platform adapters  |
| MoviePy `VideoFileClip` assembly    | `reels render` pure-ffmpeg `filter_complex` graph              |
| Music *replaced* clip audio         | music *ducked* under clip audio (`sidechaincompress`)          |
| "exit 0" meant done                 | `reels verify` / `reels prove` return three verdicts (0/5/7)   |
| YAML metadata files                 | normalized `capture.json` + `reel.json` documents              |

## Kando / Obsidian integration (preserved in spirit)

A quick one-shot can still kick off a capture; it now calls the agent-drivable
CLI instead of a shell script that summons OBS:

```bash
reels capture --out ~/reel/shots --name demo --region monitor:0 --audio --json
```

The Obsidian-vault folder conventions you already use for sorting reels are
unchanged — the folder is just a place the documents and media live, not a
contract enforced by scripts.
