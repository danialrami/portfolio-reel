#!/usr/bin/env python3

import os
import sys
import yaml
import argparse
from pathlib import Path
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, concatenate_videoclips, AudioFileClip
from moviepy.video.fx.fadein import fadein
from moviepy.video.fx.fadeout import fadeout

def create_reel(reel_type, year, background_music=None, output_dir=None, config_file=None):
    """
    Create a reel from video clips and their metadata.
    
    Args:
        reel_type (str): Type of reel (e.g., 'sound-design', 'composition')
        year (str): Year of the reel
        background_music (str, optional): Path to background music file
        output_dir (str, optional): Directory to save the output reel
        config_file (str, optional): Path to a configuration file for global settings
    """
    # Define base directory structure
    base_dir = Path(f"reel/{reel_type}/{year}")
    
    if not base_dir.exists():
        print(f"Error: Directory {base_dir} does not exist")
        return
    
    # Load configuration file if provided, or check for default config in the reel directory
    config = {}
    if config_file and Path(config_file).exists():
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
    elif (base_dir / "config.yaml").exists():
        with open(base_dir / "config.yaml", 'r') as f:
            config = yaml.safe_load(f)
    
    # Use background music from config if not provided as argument
    if not background_music and 'background_music' in config:
        background_music = config['background_music']
    
    # Find all YAML files in the directory (excluding config.yaml)
    yaml_files = [f for f in sorted(base_dir.glob("*.yaml")) if f.name != "config.yaml"]
    
    if not yaml_files:
        print(f"No YAML files found in {base_dir}")
        return
    
    # Process each project
    projects = []
    for yaml_file in yaml_files:
        with open(yaml_file, 'r') as f:
            project = yaml.safe_load(f)
            project['file'] = yaml_file.with_suffix('.mp4')
            projects.append(project)
    
    # Sort projects by 'order' field if present
    projects.sort(key=lambda x: x.get('order', float('inf')))
    
    processed_clips = []
    
    for project in projects:
        video_file = project['file']
        
        if not video_file.exists():
            print(f"Warning: Video file {video_file} not found, skipping")
            continue
        
        # Load and trim video
        try:
            clip = VideoFileClip(str(video_file))
            
            # Apply trimming if start/end times are provided
            if 'start' in project and 'end' in project:
                clip = clip.subclip(project.get('start', 0), project.get('end', None))
            
            # Create text overlay
            text_content = f"{project.get('title', 'Untitled Project')}"
            if 'role' in project:
                text_content += f"\n{project['role']}"
            if 'client' in project:
                text_content += f"\nClient: {project['client']}"
            if 'year' in project:
                text_content += f"\n{project['year']}"
            
            text = TextClip(
                text=text_content,
                font=config.get('font', "Arial"),
                fontsize=config.get('fontsize', 30),
                color=config.get('text_color', 'white'),
                bg_color=config.get('text_bg_color', 'rgba(0,0,0,0.5)'),
                method='caption',
                align='west',
                size=(clip.w, None)
            ).with_duration(clip.duration).with_position(('left', 'bottom'))
            
            # Combine video and text
            final_clip = CompositeVideoClip([clip, text])
            
            # Add fade effects
            fade_duration = project.get('fade_duration', config.get('fade_duration', 0.5))
            final_clip = fadein(final_clip, fade_duration)
            final_clip = fadeout(final_clip, fade_duration)
            
            processed_clips.append(final_clip)
            
        except Exception as e:
            print(f"Error processing {video_file}: {e}")
    
    if not processed_clips:
        print("No clips were processed successfully")
        return
    
    # Add intro clip if specified in config
    if 'intro_text' in config:
        intro_clip = TextClip(
            config['intro_text'],
            fontsize=config.get('intro_fontsize', 50),
            color=config.get('intro_text_color', 'white'),
            bg_color=config.get('intro_bg_color', 'black'),
            size=(1920, 1080),
            method='caption'
        ).with_duration(config.get('intro_duration', 5))
        intro_clip = fadein(intro_clip, 1).fadeout(1)
        processed_clips.insert(0, intro_clip)
    
    # Add outro clip if specified in config
    if 'outro_text' in config:
        outro_clip = TextClip(
            config['outro_text'],
            fontsize=config.get('outro_fontsize', 50),
            color=config.get('outro_text_color', 'white'),
            bg_color=config.get('outro_bg_color', 'black'),
            size=(1920, 1080),
            method='caption'
        ).with_duration(config.get('outro_duration', 5))
        outro_clip = fadein(outro_clip, 1).fadeout(1)
        processed_clips.append(outro_clip)
    
    # Concatenate all clips
    reel = concatenate_videoclips(processed_clips, method='compose')
    
    # Add background music if provided
    if background_music and os.path.exists(background_music):
        try:
            bg_audio = AudioFileClip(background_music).subclip(0, reel.duration)
            bg_volume = config.get('background_volume', 0.2)
            bg_audio = bg_audio.volumex(bg_volume)
            
            # Mix with original audio
            reel = reel.with_audio(bg_audio)
        except Exception as e:
            print(f"Error adding background music: {e}")
    
    # Determine output path
    output_filename = config.get('output_filename', f"{reel_type}_reel_{year}.mp4")
    if output_dir:
        output_path = Path(output_dir) / output_filename
    else:
        output_path = base_dir / output_filename
    
    # Create output directory if it doesn't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Export final reel
    print(f"Rendering reel to {output_path}...")
    reel.write_videofile(str(output_path), 
                         fps=config.get('fps', 30), 
                         codec=config.get('video_codec', 'libx264'), 
                         audio_codec=config.get('audio_codec', 'aac'))
    print(f"Reel created successfully: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a reel from video clips and metadata")
    parser.add_argument("reel_type", help="Type of reel (e.g., 'sound-design', 'composition')")
    parser.add_argument("year", help="Year of the reel")
    parser.add_argument("--background", "-b", help="Path to background music file")
    parser.add_argument("--output", "-o", help="Directory to save the output reel")
    parser.add_argument("--config", "-c", help="Path to configuration file")
    
    args = parser.parse_args()
    
    create_reel(args.reel_type, args.year, args.background, args.output, args.config)
