#!/bin/bash

# Portfolio Clip Capture Script
# This script runs the Python capture script and ensures proper YAML generation

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PYTHON_SCRIPT="$SCRIPT_DIR/capture_portfolio_clip.py"

# Check if the Python script exists
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Error: $PYTHON_SCRIPT not found."
    echo "Please ensure the script is in the same directory as this bash script."
    exit 1
fi

# Check if OBS is running; start it if not
if ! pgrep -x "obs" > /dev/null; then
    echo "Warning: OBS doesn't appear to be running. Starting OBS..."
    obs --minimize-to-tray &
    sleep 3  # Give OBS time to start
fi

# Check if obs-cli is installed
if ! command -v obs-cli &> /dev/null; then
    echo "Error: obs-cli is not installed or not in PATH."
    echo "Please install obs-cli to control OBS programmatically."
    exit 1
fi

# Ensure the uv environment with dependencies is ready
echo "Checking dependencies (uv)..."
uv run --project "$SCRIPT_DIR" python -c "import inquirer, yaml" 2>/dev/null || {
    echo "Installing dependencies with uv..."
    uv sync --project "$SCRIPT_DIR"
}

# Run the Python script
echo "Starting portfolio clip capture..."
uv run --project "$SCRIPT_DIR" python "$PYTHON_SCRIPT"

# Check if the script executed successfully
if [ $? -eq 0 ]; then
    echo "✓ Recording and YAML generation completed successfully."
    echo "Your portfolio clip has been saved and is ready for inclusion in your reel."
else
    echo "✗ Error: Something went wrong during the recording process."
    exit 1
fi

exit 0
