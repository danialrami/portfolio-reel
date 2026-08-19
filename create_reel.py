#!/usr/bin/env python3
"""Compile trimmed portfolio clips into a reel with text overlays, fades,
intro/outro and ducked background music.

MoviePy 2.x API. The clip's own audio is preserved and mixed under the
background music rather than replaced.
"""

import os
import sys
import argparse
from pathlib import Path

import yaml
from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
)
from moviepy import afx, vfx


def load_config(base_dir, config_file):
    """Load the global/reel config from an explicit file or the sibling config.yaml."""
    config = {}
    if config_file and Path(config_file).exists():
        with open(config_file, "r") as f:
            config = yaml.safe_load(f) or {}
    elif (base_dir / "config.yaml").exists():
        with open(base_dir / "config.yaml", "r") as f:
            config = yaml.safe_load(f) or {}
    return config


def resolve_font(config, key="font"):
    """Return a configured font or None (PIL default). Invalid fonts crash PIL, so only
    pass one through if it is actually loadable."""
    font = config.get(key)
    if not font:
        return None
    try:
        from PIL import ImageFont
        ImageFont.truetype(font)
        return font
    except Exception:
        print(f"Warning: font '{font}' not loadable, using default", file=sys.stderr)
        return None


def make_overlay(video, project, config):
    """Build the per-clip text overlay (multi-line caption, bottom-left)."""
    text_content = project.get("title", "Untitled Project")
    role = project.get("role")
    client = project.get("client")
    year = project.get("year")
    if role:
        text_content += f"\n{role}"
    if client:
        text_content += f"\nClient: {client}"
    if year:
        text_content += f"\n{year}"

    size = (int(video.w), None)
    return (
        TextClip(
            text=text_content,
            font=resolve_font(config),
            font_size=config.get("fontsize", 30),
            color=config.get("text_color", "white"),
            bg_color=config.get("text_bg_color", None),
            method="caption",
            text_align="left",
            size=size,
            duration=video.duration,
            interline=4,
        )
        .with_position(("left", "bottom"), relative=True)
        .with_start(0)
    )


def build_intro_outro_text(text, config, key_prefix, default_duration):
    """Intro/outro full-frame title cards."""
    duration = config.get(f"{key_prefix}duration", default_duration)
    return (
        TextClip(
            text=text,
            font=resolve_font(config),
            font_size=config.get(f"{key_prefix}fontsize", 50),
            color=config.get(f"{key_prefix}text_color", "white"),
            bg_color=config.get(f"{key_prefix}bg_color", "black"),
            method="caption",
            size=(1920, 1080),
            duration=duration,
        )
        .with_effects([vfx.FadeIn(1), vfx.FadeOut(1)])
    )


def create_reel(reel_type, year, background_music=None, output_dir=None, config_file=None):
    """Build a reel from the YAML metadata + sibling .mp4 clips in reel/<type>/<year>/."""
    base_dir = Path("reel") / reel_type / year
    if not base_dir.exists():
        print(f"Error: Directory {base_dir} does not exist", file=sys.stderr)
        return 1

    config = load_config(base_dir, config_file)
    if not background_music:
        background_music = config.get("background_music")

    yaml_files = [f for f in sorted(base_dir.glob("*.yaml")) if f.name != "config.yaml"]
    if not yaml_files:
        print(f"No YAML files found in {base_dir}", file=sys.stderr)
        return 1

    projects = []
    for yaml_file in yaml_files:
        with open(yaml_file, "r") as f:
            project = yaml.safe_load(f)
            project["file"] = yaml_file.with_suffix(".mp4")
            projects.append(project)
    projects.sort(key=lambda x: x.get("order", float("inf")))

    processed = []
    for project in projects:
        video_file = project["file"]
        if not video_file.exists():
            print(f"Warning: Video file {video_file} not found, skipping")
            continue
        try:
            clip = VideoFileClip(str(video_file))
            start = project.get("start", 0)
            end = project.get("end")
            if start is not None and end is not None:
                clip = clip.subclipped(start, end)

            overlay = make_overlay(clip, project, config)
            final_clip = CompositeVideoClip([clip, overlay])

            fade = project.get("fade_duration", config.get("fade_duration", 0.5))
            final_clip = final_clip.with_effects([vfx.FadeIn(fade), vfx.FadeOut(fade)])
            processed.append(final_clip)
        except Exception as e:
            print(f"Error processing {video_file}: {e}", file=sys.stderr)

    if not processed:
        print("No clips processed successfully", file=sys.stderr)
        return 1

    if config.get("intro_text"):
        processed.insert(0, build_intro_outro_text(config["intro_text"], config, "intro_", 5))
    if config.get("outro_text"):
        processed.append(build_intro_outro_text(config["outro_text"], config, "outro_", 5))

    reel = concatenate_videoclips(processed, method="compose")

    # Mix background music under the clip audio (do not replace it).
    if background_music and os.path.exists(background_music):
        try:
            bg = AudioFileClip(background_music).subclipped(0, reel.duration)
            bg = bg.with_effects([afx.MultiplyVolume(config.get("background_volume", 0.2))])
            if reel.audio is not None:
                mixed = CompositeAudioClip([reel.audio, bg])
            else:
                mixed = bg
            reel = reel.with_audio(mixed)
        except Exception as e:
            print(f"Error adding background music: {e}", file=sys.stderr)

    output_filename = config.get("output_filename", f"{reel_type}_reel_{year}.mp4")
    output_path = (Path(output_dir) if output_dir else base_dir) / output_filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Rendering reel to {output_path}...")
    reel.write_videofile(
        str(output_path),
        fps=config.get("fps", 30),
        codec=config.get("video_codec", "libx264"),
        audio_codec=config.get("audio_codec", "aac"),
    )
    print(f"Reel created successfully: {output_path}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Create a reel from video clips and metadata")
    parser.add_argument("reel_type", help="Reel category (e.g. sound-design)")
    parser.add_argument("year", help="Year of the reel")
    parser.add_argument("--background", "-b", help="Path to background music file")
    parser.add_argument("--output", "-o", help="Directory to save the output reel")
    parser.add_argument("--config", "-c", help="Path to configuration file")
    args = parser.parse_args()
    sys.exit(create_reel(args.reel_type, args.year, args.background, args.output, args.config))


if __name__ == "__main__":
    main()
