# README: Portfolio Reel Generator Workflow

## Overview

This system provides a streamlined workflow for creating professional portfolio reels from day-to-day work. It consists of two main components:

1. **Clip Capture Tool**: Records video clips of your work and generates metadata files
2. **Reel Generator**: Compiles your clips into a reel with text overlays and transitions

The workflow is designed to integrate with an Obsidian vault and minimize friction in the portfolio creation process.

## Setup

### Prerequisites

- Python 3.7+
- OBS Studio
- obs-cli (for controlling OBS programmatically)
- MoviePy and other Python dependencies

### Installation

1. Create a directory structure in your Obsidian vault:
   ```
   obsidian-vault/
   ├── reel/
   │   ├── sound-design/
   │   │   ├── 2025/
   │   ├── composition/
   │   ├── implementation/
   ```

2. Copy the scripts to a convenient location:
   - `create-reel.py`: The main reel generator script
   - `capture-portfolio-clip.py`: The clip capture script
   - `run-capture.sh`: The bash script to run the capture tool

3. Install required Python packages:
   ```bash
   pip install moviepy inquirer pyyaml obs-cli
   ```

4. Install obs-cli:
   ```bash
   # Follow installation instructions at https://github.com/obsproject/obs-cli
   ```

5. Make the bash script executable:
   ```bash
   chmod +x run_capture.sh
   ```

6. Configure OBS:
   - Create a scene for portfolio captures
   - Set up your recording output path (default: ~/Videos)
   - Configure hotkeys if desired

## Step-by-Step Guide

### 1. Capturing Portfolio Clips

When you create something you want to include in your portfolio:

1. Run the capture script:
   ```bash
   ./run_capture.sh
   ```

2. Enter the project details when prompted:
   - Project title
   - Client name
   - Your role (defaults to "Sound Designer")
   - Reel category (sound-design, composition, implementation)

3. The script will start OBS recording. Do your demonstration, then press Enter to stop recording.

4. The script will:
   - Save the recording to the appropriate directory
   - Generate a YAML metadata file
   - Assign the next available order number

### 2. Creating Configuration Files (Optional)

For each reel type, you can create a `config.yaml` file with global settings:

```yaml
# Visual settings
font: "Arial"
fontsize: 30
text_color: "white"
text_bg_color: "rgba(0,0,0,0.5)"
fade_duration: 0.7

# Intro/Outro
intro_text: "NAME\nSound Design Portfolio\nYYYY"
intro_duration: 5
intro_fontsize: 60
intro_bg_color: "black"

outro_text: "Contact: your@email.com\nwww.yourwebsite.com"
outro_duration: 7
outro_fontsize: 50
outro_bg_color: "black"

# Audio settings
background_music: "assets/reel_background.mp3"
background_volume: 0.15

# Output settings
output_filename: "reel_name_SoundDesign_YYYY.mp4"
fps: 30
video_codec: "libx264"
audio_codec: "aac"
```

Place this file in the reel directory (e.g., `reel/sound-design/2025/config.yaml`).

### 3. Editing Project Metadata

You can manually edit the YAML files to adjust:
- Start/end times for trimming
- Project details
- Order of appearance in the reel

Example YAML file (`reel/sound-design/2025/1.yaml`):
```yaml
title: "Ambient Sound Design for VR Experience"
role: "Sound Designer"
client: "Metaverse Studios"
year: 2025
order: 1
start: 10
end: 40
fade_duration: 0.5
```

### 4. Generating Reels

When you're ready to create your reel:

1. Run the reel generator script:
   ```bash
   python create_reel.py sound-design 2025
   ```

2. Optional arguments:
   - `--background` or `-b`: Path to background music
   - `--output` or `-o`: Custom output directory
   - `--config` or `-c`: Path to custom config file

3. The script will:
   - Process all clips in the specified directory
   - Apply text overlays and transitions
   - Add intro/outro if specified
   - Add background music if provided
   - Export the final reel

### 5. Integration with [Kando Pie Menu](https://kando.menu/)

Quickly capture portfolio clips with a few clicks

To integrate with Kando:

1. Add a new action to your Kando pie menu
2. Set the action to run: `/path/to/run_capture.sh`
3. Assign an icon and label (e.g., "Capture Portfolio Clip")

## Advanced Usage

### Custom Ordering

The `order` field in each YAML file determines the sequence of clips in the reel. Lower numbers appear first.

### Multiple Reel Types

You can maintain different types of reels (sound-design, composition, implementation) with separate configurations.

### Background Music

Add background music to your reel by:
1. Specifying it in the config file: `background_music: "path/to/music.mp3"`
2. Passing it as an argument: `python create_reel.py sound-design 2025 -b path/to/music.mp3`

### Custom Output

Change the output filename and location:
1. In config: `output_filename: "MyCustomReel.mp4"`
2. Command line: `python create_reel.py sound-design 2025 -o /path/to/output`

## Workflow Tips

1. **Capture as You Go**: Record portfolio clips right after completing significant work while it's still fresh
2. **Consistent Naming**: Use descriptive project titles that will make sense in your reel
3. **Regular Updates**: Regenerate your reels quarterly to keep them current
4. **Backup**: Ensure your reel directory is backed up with your Obsidian vault
5. **Review and Refine**: Periodically review your clips and adjust trimming as needed

## Troubleshooting

- **OBS Not Starting**: Ensure OBS is installed and in your PATH
- **Missing Dependencies**: Run `pip install moviepy inquirer pyyaml obs-cli` to install required packages
- **Recording Issues**: Check OBS settings and ensure you have write permissions to the output directory
- **YAML Errors**: Ensure your YAML files are properly formatted
- **Video Processing Errors**: Check that MoviePy can process your video format

## File Structure

```
obsidian-vault/
├── reel/
│   ├── sound-design/
│   │   ├── 2025/
│   │   │   ├── 1.mp4
│   │   │   ├── 1.yaml
│   │   │   ├── 2.mp4
│   │   │   ├── 2.yaml
│   │   │   ├── config.yaml
│   │   │   └── sound-design_reel_2025.mp4
│   ├── composition/
│   │   ├── 2025/
│   │   │   └── ...
│   ├── implementation/
│   │   ├── 2025/
│   │   │   └── ...
├── scripts/
│   ├── create_reel.py
│   ├── capture_portfolio_clip.py
│   └── run_capture.sh
```

## Customization

Feel free to modify the scripts to better suit your workflow. Some ideas:
- Add more metadata fields to your YAML files
- Create custom text overlay styles
- Implement different transition types
- Add watermarks or logos to your reels