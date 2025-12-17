# BPMN Timelapse Creator

Generate timelapse videos showing the evolution of a BPMN file through its git history. Each frame represents a commit that modified the file, allowing you to visualize how a process diagram evolved over time.

## Prerequisites

- Python 3.6+
- Git
- Node.js (for bpmn-to-image)
- ffmpeg (`brew install ffmpeg`)
- librsvg (`brew install librsvg`)

## Installation

```bash
# Install bpmn-to-image
npm install -g bpmn-to-image

# Install system dependencies (macOS)
brew install ffmpeg librsvg
```

## Usage

```bash
python bpmn_to_timelapse.py <filename> <repo_path> [options]
```

**Required arguments:**
- `filename` - Name of the BPMN file to track (e.g., `my_process.bpmn`)
- `repo_path` - Path to the git repository containing the file

**Optional arguments:**
- `-o, --output FILE` - Output video path (default: `<filename>_timelapse.mp4`)
- `--since YYYY-MM-DD` - Only include commits after this date
- `--until YYYY-MM-DD` - Only include commits before this date
- `--width N` - Canvas width in pixels (default: 1920)
- `--height N` - Canvas height in pixels (default: 1080)
- `--fps N` - Frames per second (default: 5, ignored if --audio provided)
- `--batch-size N` - Files per conversion batch (default: 50)
- `--no-overlay` - Disable commit date/message overlay on frames
- `--audio FILE` - Add soundtrack and sync video length to audio duration

## Examples

```bash
# Generate timelapse for entire git history with default settings
python bpmn_to_timelapse.py my_process.bpmn /path/to/repo

# Generate timelapse for last 6 months at 1440p
python bpmn_to_timelapse.py my_process.bpmn /path/to/repo --since 2024-06-01 --width 2560 --height 1440

# Custom output filename and faster playback
python bpmn_to_timelapse.py my_process.bpmn /path/to/repo -o evolution.mp4 --fps 10

# Add soundtrack (video length syncs to audio duration)
python bpmn_to_timelapse.py my_process.bpmn /path/to/repo --audio /path/to/music.mp3

# Clean frames without overlay text
python bpmn_to_timelapse.py my_process.bpmn /path/to/repo --no-overlay
```

## How It Works

1. **Phase 1**: Extracts all versions of the BPMN file from git history (follows renames)
2. **Phase 2**: Batch converts BPMN files to SVG using bpmn-to-image
3. **Phase 3**: Converts SVGs to PNGs at fixed canvas size with centered diagrams
4. **Phase 4**: Compiles frames into an MP4 video using ffmpeg

## Features

- **Rename tracking**: Follows file renames/moves through git history
- **Batched conversion**: Processes multiple files per browser launch for better performance
- **Fixed canvas size**: All frames have consistent dimensions for smooth video playback
- **Progress logging**: Shows timing for each phase and batch operation
- **Automatic cleanup**: Temporary files are cleaned up after each step

## Notes

- The file must exist in the current HEAD of the repository
- Only commits on the `main` branch are considered
