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

The tool uses a two-step workflow: first generate frames, then create the video.

### Step 1: Generate Frames

```bash
python bpmn_to_timelapse.py generate <filename> <repo_path> [options]
```

**Required arguments:**
- `filename` - Name of the BPMN file to track (e.g., `my_process.bpmn`)
- `repo_path` - Path to the git repository containing the file

**Optional arguments:**
- `--since YYYY-MM-DD` - Only include commits after this date
- `--until YYYY-MM-DD` - Only include commits before this date
- `--width N` - Canvas width in pixels (default: 1920)
- `--height N` - Canvas height in pixels (default: 1080)
- `--batch-size N` - Files per conversion batch (default: 50)

### Step 2: Create Video

```bash
python bpmn_to_timelapse.py video [options]
```

**Optional arguments:**
- `-o, --output FILE` - Output video path (default: `timelapse.mp4`)
- `--fps N` - Frames per second (default: 2)

## Examples

```bash
# Generate frames for entire git history at 1080p
python bpmn_to_timelapse.py generate my_process.bpmn /path/to/repo

# Generate frames for last 6 months at 1440p
python bpmn_to_timelapse.py generate my_process.bpmn /path/to/repo \
    --since 2024-06-01 --width 2560 --height 1440

# Create video at 4 fps
python bpmn_to_timelapse.py video --fps 4

# Create video with custom name
python bpmn_to_timelapse.py video -o my_process_evolution.mp4
```

## How It Works

1. **Phase 1**: Extracts all versions of the BPMN file from git history (follows renames)
2. **Phase 2**: Batch converts BPMN files to SVG using bpmn-to-image (single browser session for performance)
3. **Phase 3**: Converts SVGs to PNGs at fixed canvas size with centered diagrams
4. **Video**: Compiles frames into an MP4 video using ffmpeg

## Features

- **Rename tracking**: Follows file renames/moves through git history
- **Batched conversion**: Processes multiple files per browser launch for better performance
- **Fixed canvas size**: All frames have consistent dimensions for smooth video playback
- **Progress logging**: Shows timing for each phase and batch operation
- **Automatic cleanup**: Temporary files are cleaned up after each step

## Notes

- The file must exist in the current HEAD of the repository
- Only commits on the `main` branch are considered
