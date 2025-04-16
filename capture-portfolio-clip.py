#!/usr/bin/env python3

import subprocess
import os
import yaml
import datetime
from pathlib import Path
import inquirer  # pip install inquirer

def capture_portfolio_clip():
    # Ask for project details
    questions = [
        inquirer.Text('title', message="Project title"),
        inquirer.Text('client', message="Client name"),
        inquirer.Text('role', message="Your role", default="Sound Designer"),
        inquirer.List('reel_type', 
                     message="Reel category",
                     choices=['sound-design', 'composition', 'implementation']),
    ]
    answers = inquirer.prompt(questions)
    
    # Create timestamp and filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{answers['title'].replace(' ', '_').lower()}"
    
    # Start OBS recording
    print("Starting recording... (Press Ctrl+C to stop)")
    try:
        # Start OBS recording (requires obs-cli or similar)
        subprocess.run(["obs-cli", "recording", "start"])
        
        # Wait for user to stop recording
        input("Press Enter to stop recording...")
        
        # Stop recording
        subprocess.run(["obs-cli", "recording", "stop"])
        
        # Get the latest recording file from OBS
        # This depends on your OBS setup, you might need to adjust
        obs_output_dir = Path.home() / "Videos"
        latest_recording = max(obs_output_dir.glob("*.mp4"), key=os.path.getctime)
        
        # Create reel directory if it doesn't exist
        year = datetime.datetime.now().strftime("%Y")
        reel_dir = Path(f"reel/{answers['reel_type']}/{year}")
        reel_dir.mkdir(parents=True, exist_ok=True)
        
        # Find the next available order number
        existing_yamls = list(reel_dir.glob("*.yaml"))
        next_order = 1
        if existing_yamls:
            for yaml_file in existing_yamls:
                with open(yaml_file, 'r') as f:
                    data = yaml.safe_load(f)
                    if 'order' in data and data['order'] >= next_order:
                        next_order = data['order'] + 1
        
        # Create YAML file
        yaml_data = {
            'title': answers['title'],
            'role': answers['role'],
            'client': answers['client'],
            'year': int(year),
            'order': next_order,
            'start': 0,
            'end': None  # Use full clip length
        }
        
        # Save YAML file
        yaml_path = reel_dir / f"{next_order}.yaml"
        with open(yaml_path, 'w') as f:
            yaml.dump(yaml_data, f, default_flow_style=False)
        
        # Copy video file
        video_path = reel_dir / f"{next_order}.mp4"
        subprocess.run(["cp", str(latest_recording), str(video_path)])
        
        print(f"Clip and metadata saved to {reel_dir}")
        print(f"YAML: {yaml_path}")
        print(f"Video: {video_path}")
        
    except KeyboardInterrupt:
        print("Recording cancelled")
        subprocess.run(["obs-cli", "recording", "stop"])

if __name__ == "__main__":
    capture_portfolio_clip()
