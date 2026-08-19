"""Pure-ffmpeg renderer: turn a Reel Document into the final video (reels render).

Trims, fades, ``drawtext`` overlays, intro/outro, and ordered video concat are
expressed as a single ``filter_complex`` graph — no MoviePy, no ImageMagick, no
OBS. The preliminary background-music ducking graph is retained for a later,
explicitly verified audio phase and is not part of phases 0/1.

Output is staged in a temp dir then atomically moved to the destination, so a
failed render never leaves a half-written file where the user asked for one.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from .capture_doc import load_capture
from .errors import Exit, ExitCodes
from .media import _require
from .reel_doc import Reel, load_reel

W = 1920
H = 1080
FPS = 30
FADEFALLBACK = 0.5


def _stream_has_audio(path: Path) -> bool:
    _require("ffprobe")
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return bool(proc.stdout.strip())


def _media_duration(path: Path) -> float:
    _require("ffprobe")
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def _esc_text(text: str) -> str:
    """Escape a value for use inside a drawtext=... text= value."""
    return (
        text.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("\n", "\\n")
    )


def _overlay_filter(text: str, position: str, fade: float) -> str:
    t = _esc_text(text)
    pos = position
    # position -> x:y (relative to W/H)
    if pos == "center":
        x, y = "x=(w-text_w)/2", "y=(h-text_h)/2"
    elif pos == "top-left":
        x, y = "x=20", "y=20"
    elif pos == "top-right":
        x, y = "x=w-tw-20", "y=20"
    elif pos == "bottom-right":
        x, y = "x=w-tw-20", "y=h-th-20"
    else:  # bottom-left (default)
        x, y = "x=20", "y=h-th-20"
    return (
        f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        f":text='{t}':fontsize=42:fontcolor=white:borderw=2:bordercolor=black"
        f":box=1:boxcolor=black@0.5:boxborderw=12:{x}:{y}"
    )


def _fade(duration: float, fade: float) -> str:
    fade = fade if fade > 0 else FADEFALLBACK
    if duration <= fade * 2:
        # tiny segment: single crossfade
        return f"fade=t=in:st=0:d={fade}"
    return f"fade=t=in:st=0:d={fade},fade=t=out:st={round(duration - fade, 3)}:d={fade}"


def build_filter_graph(
    reel: Reel,
    clip_paths: list[Path],
    clip_durations: list[float],
    has_audio: list[bool],
    music_path: Path | None,
    music_has_audio: bool,
) -> str:
    parts: list[str] = []
    video_pads: list[str] = []
    audio_pads: list[str] = []

    n = len(clip_paths)            # input indices 0..n-1 are clips
    intro_on = bool(reel.intro.text and reel.intro.duration > 0)
    outro_on = bool(reel.outro.text and reel.outro.duration > 0)
    intro_idx = n                  # intro is input n
    outro_idx = n + (1 if intro_on else 0)
    music_idx = n + (1 if intro_on else 0) + (1 if outro_on else 0)
    fade = reel.style.fade_duration

    # intro
    if intro_on:
        parts.append(
            f"[{intro_idx}:v]drawtext=text='{_esc_text(reel.intro.text)}'"
            f":fontsize=64:fontcolor=white:borderw=2:bordercolor=black"
            f":x=(w-text_w)/2:y=(h-text_h)/2,{_fade(reel.intro.duration, fade)}"
            f",fps={reel.output.fps},scale={reel.output.size},setsar=1[vintro]"
        )
        video_pads.append("[vintro]")

    # clips
    for i in range(n):
        seg = reel.clips[i]
        dur = clip_durations[i]
        vf = f"[{i}:v]trim={_trim_lbl(seg)},setpts=PTS-STARTPTS" \
             f",fps={reel.output.fps},scale={reel.output.size},setsar=1"
        if seg.overlay and seg.overlay.text:
            vf += "," + _overlay_filter(seg.overlay.text, seg.overlay.position, fade)
        vf += f",{_fade(dur, fade)}[v{i}]"
        parts.append(vf)
        video_pads.append(f"[v{i}]")
        if has_audio[i]:
            af = (f"[{i}:a]atrim={_trim_lbl(seg, audio=True)},asetpts=PTS-STARTPTS"
                  f",aresample=48000[a{i}]")
            parts.append(af)
            audio_pads.append(f"[a{i}]")

    # outro
    if outro_on:
        parts.append(
            f"[{outro_idx}:v]drawtext=text='{_esc_text(reel.outro.text)}'"
            f":fontsize=64:fontcolor=white:borderw=2:bordercolor=black"
            f":x=(w-text_w)/2:y=(h-text_h)/2,{_fade(reel.outro.duration, fade)}"
            f",fps={reel.output.fps},scale={reel.output.size},setsar=1[voutro]"
        )
        video_pads.append("[voutro]")

    # concat video
    nv = len(video_pads)
    parts.append(f"{''.join(video_pads)}concat=n={nv}:v=1:a=0[vout]")

    # concat audio (clips only)
    if audio_pads:
        m = len(audio_pads)
        parts.append(f"{''.join(audio_pads)}concat=n={m}:v=0:a=1[aout]")

    # music ducking: compress the music (main) with clip audio as the
    # sidechain, then mix the (unattenuated) speech back with the ducked music.
    # Music is trimmed to the expected reel length; speech is asplit so it can
    # feed both the sidechain and the final mix (a label is consumed once).
    expected_total = sum(clip_durations) + (reel.intro.duration if intro_on else 0.0) \
        + (reel.outro.duration if outro_on else 0.0)
    if music_path and music_has_audio and audio_pads:
        parts.append(
            f"[{music_idx}:a]atrim=end={round(max(expected_total, 0.1), 3)},asetpts=PTS-STARTPTS[a_mus];"
            "[aout]asplit=2[sp1][sp2];"
            "[a_mus][sp1]sidechaincompress="
            "threshold=0.05:ratio=8:attack=50:release=500[ducked];"
            f"[ducked][sp2]amix=inputs=2:duration=first:normalize=0:dropout_transition=2:"
            f"weights='{reel.music.volume} 1'[aoutmix]"
        )

    return ";".join(parts)


def _trim_lbl(seg, audio: bool = False) -> str:
    if audio:
        return f"start={round(seg.trim_in, 3)}:end={round(seg.trim_out, 3)}" if seg.trim_out > 0 else f"start={round(seg.trim_in, 3)}"
    return f"start={round(seg.trim_in, 3)}:end={round(seg.trim_out, 3)}" if seg.trim_out > 0 else f"start={round(seg.trim_in, 3)}"


def resolve_clip_media(reel_path: Path, reel: Reel, captures_root: Path | None) -> list[Path]:
    root = captures_root or reel_path.parent
    media: list[Path] = []
    for clip in sorted(reel.clips, key=lambda c: c.order):
        cap = None
        for p in sorted(root.rglob("capture.json")) + sorted(root.rglob("*.capture.json")):
            try:
                cand = load_capture(p)
            except (OSError, ValueError):
                continue
            if cand.capture_id == clip.capture_ref:
                cap = cand
                break
        if cap is None or not cap.file:
            raise Exit(ExitCodes.SOURCE,
                       f"could not resolve media for capture {clip.capture_ref!r}")
        f = Path(cap.file)
        if not f.exists():
            raise Exit(ExitCodes.SOURCE, f"media missing for {clip.capture_ref!r}: {f}")
        media.append(f)
    return media


def _build_args(reel: Reel, clip_paths: list[Path], music_path: Path | None,
                out: Path, filter_str: str, final_audio: str | None,
                intro_on: bool, outro_on: bool) -> list[str]:
    args = ["ffmpeg", "-y"]

    # clip inputs
    for p in clip_paths:
        args += ["-i", str(p)]
    if intro_on:
        args += ["-f", "lavfi", "-i", f"color=c=black:s={reel.output.size}:r={reel.output.fps}:d={reel.intro.duration}"]
    if outro_on:
        args += ["-f", "lavfi", "-i", f"color=c=black:s={reel.output.size}:r={reel.output.fps}:d={reel.outro.duration}"]
    if music_path:
        args += ["-i", str(music_path)]

    args += ["-filter_complex", filter_str, "-map", "[vout]"]
    if final_audio:
        args += ["-map", final_audio]
    args += ["-r", str(reel.output.fps), "-c:v", reel.output.video_codec,
             "-pix_fmt", "yuv420p"]
    if final_audio:
        args += ["-c:a", reel.output.audio_codec]
    # strip timestamps/metadata and force bit-exactness so equal inputs
    # -> byte-identical renders (determinism is a Contract-two relation)
    args += ["-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
             "-map_metadata", "-1", str(out)]
    return args


def render(reel_path: Path, out: Path, dry_run: bool = False,
           captures_root: Path | None = None) -> int:
    reel = load_reel(reel_path)
    if reel.music.file:
        raise Exit(
            ExitCodes.NOT_IMPLEMENTED,
            "music/audio rendering is deferred to a later verified audio phase",
        )
    try:
        clip_paths = resolve_clip_media(reel_path, reel, captures_root)
    except Exit:
        if dry_run:
            # dry-run only needs to show the graph/command, not real media
            clip_paths = [Path("clip.mp4") for _ in reel.clips]
        else:
            raise
    ordered = sorted(reel.clips, key=lambda c: c.order)
    clip_durations = []
    for c, p in zip(ordered, clip_paths):
        if c.trim_out > c.trim_in:
            clip_durations.append(c.trim_out - c.trim_in)
        else:
            # trim_out unset (0) -> use the clip's real duration
            clip_durations.append(max(0.0, _media_duration(p) - c.trim_in))
    has_audio = [_stream_has_audio(p) for p in clip_paths]
    if dry_run and (not clip_paths or all(p == Path("clip.mp4") for p in clip_paths)):
        has_audio = [True] * len(clip_paths)  # best-effort graph for dry-run
    if any(has_audio) and not dry_run:
        raise Exit(
            ExitCodes.NOT_IMPLEMENTED,
            "audio streams in reel inputs are deferred to a later verified audio phase",
        )

    music_path = Path(reel.music.file) if reel.music.file else None
    music_has_audio = bool(music_path and music_path.exists() and _stream_has_audio(music_path))

    intro_on = bool(reel.intro.text and reel.intro.duration > 0)
    outro_on = bool(reel.outro.text and reel.outro.duration > 0)

    filter_str = build_filter_graph(reel, clip_paths, clip_durations, has_audio,
                                    music_path, music_has_audio)
    # final_audio decision mirrors build_filter_graph
    audio_pads_count = sum(has_audio)
    final_audio = None
    if audio_pads_count:
        final_audio = "[aoutmix]" if (music_path and music_has_audio) else "[aout]"

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if dry_run:
        args = _build_args(reel, clip_paths, music_path, out, filter_str,
                           final_audio, intro_on, outro_on)
        print(json.dumps({"dry_run": True, "out": str(out), "ffmpeg": args,
                          "filter_complex": filter_str}, indent=2))
        return ExitCodes.OK

    # stage to a temp file in the dest dir, then move (atomic-ish)
    fd, tmp = tempfile.mkstemp(suffix=".mp4", dir=out.parent)
    import os
    os.close(fd)
    tmp = Path(tmp)
    args = _build_args(reel, clip_paths, music_path, tmp, filter_str,
                       final_audio, intro_on, outro_on)
    try:
        proc = subprocess.run(args, capture_output=True, text=True)
    except FileNotFoundError:
        raise Exit(ExitCodes.MISSING_BINARY, "ffmpeg not found")
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise Exit(ExitCodes.SOURCE, f"render failed: {proc.stderr[-500:]}")
    shutil.move(str(tmp), str(out))
    return ExitCodes.OK


def cmd_render(args) -> int:
    reel_path = Path(args.reel)
    if not reel_path.exists():
        raise Exit(ExitCodes.USAGE, f"reel document not found: {reel_path}")
    out = Path(args.out) if args.out else Path(args.reel).parent / "Reel.mp4"
    captures_root = Path(getattr(args, "captures", "."))
    return render(reel_path, out, dry_run=args.dry_run, captures_root=captures_root)


from .cli import register  # noqa: E402

register("render", cmd_render)
