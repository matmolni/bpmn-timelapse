# BPMN Timelapse Creator

This script creates a timelapse video from a series of BPMN files, ordered by their git commit dates.

## Prerequisites

1. Python 3.6+
2. Git installed and available in PATH
3. Node.js (required for bpmn-to-image)

## Installation

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Install bpmn-to-image globally:
   ```bash
   npm install -g bpmn-to-image
   ```

## Usage

1. Place your BPMN files in a directory called `bpmn_files/` in the same directory as the script.
2. Run the script:
   ```bash
   python bpmn_to_timelapse.py
   ```
3. The script will:
   - Convert all BPMN files to PNG images
   - Sort them by their git commit dates
   - Create a timelapse video called `bpmn_timelapse.mp4`

## Output

- `output_images/`: Directory containing the generated PNG files
- `bpmn_timelapse.mp4`: The final timelapse video

## Customization

You can modify these variables in the script:
- `fps`: Frames per second in the output video (default: 2)
- `output_video`: Name of the output video file (default: 'bpmn_timelapse.mp4')

## Notes

- The script uses git to get the commit date of each BPMN file for proper ordering
- Make sure your BPMN files are tracked in git for the timestamp functionality to work
- If a file isn't in git, it will be placed at the beginning of the timelapse
