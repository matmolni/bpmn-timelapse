import os
import argparse
import subprocess
import tempfile
import shutil
import time
from datetime import datetime
from pathlib import Path


def find_file_in_repo(repo_path, filename):
    """Find the current path of a file in the repository."""
    cmd = ['git', '-C', repo_path, 'ls-files', f'**/{filename}']
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    paths = result.stdout.strip().split('\n')
    paths = [p for p in paths if p]  # Filter empty strings
    
    if not paths:
        return None
    if len(paths) > 1:
        print(f"Warning: Multiple files match '{filename}': {paths}")
        print(f"Using: {paths[0]}")
    return paths[0]


def get_commits_for_file(repo_path, filename, since=None, until=None):
    """
    Get all commits on main branch that modified the specified file.
    Uses the exact file path with --follow to properly track renames.
    Returns list of (commit_hash, timestamp, message, file_path) tuples, oldest first.
    The file_path is the actual path of the file at that commit (handles renames).
    """
    # First, find the current path of the file
    current_path = find_file_in_repo(repo_path, filename)
    if not current_path:
        print(f"Error: File '{filename}' not found in repository")
        return []
    
    print(f"Tracking file: {current_path}")
    
    # Use --name-only to get the file path at each commit (tracks renames)
    cmd = [
        'git', '-C', repo_path,
        'log', '--follow', '--format=%H %at %s', '--name-only',
        '--first-parent', 'main',
        '--', current_path
    ]
    
    if since:
        cmd.insert(4, f'--since={since}')
    if until:
        cmd.insert(4, f'--until={until}')
    
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    
    commits = []
    lines = result.stdout.strip().split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line:
            i += 1
            continue
        
        # Parse commit info line: "hash timestamp message"
        parts = line.split(' ', 2)
        if len(parts) >= 2 and len(parts[0]) == 40:  # Full commit hash
            commit_hash = parts[0]
            timestamp = int(parts[1])
            message = parts[2] if len(parts) > 2 else ''
            
            # Next non-empty line should be the file path
            i += 1
            while i < len(lines) and not lines[i]:
                i += 1
            
            if i < len(lines) and lines[i] and not lines[i].startswith(' '):
                file_path = lines[i]
                commits.append((commit_hash, timestamp, message, file_path))
            i += 1
        else:
            i += 1
    
    # Return in chronological order (oldest first)
    return list(reversed(commits))


def get_file_path_at_commit(repo_path, commit_hash, filename):
    """Find the actual path of the file at a specific commit."""
    cmd = [
        'git', '-C', repo_path,
        'ls-tree', '-r', '--name-only', commit_hash
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    
    for path in result.stdout.strip().split('\n'):
        if path.endswith(filename):
            return path
    return None


def checkout_file_version(repo_path, commit_hash, file_path, output_path):
    """Checkout a specific version of a file to a temporary location."""
    cmd = [
        'git', '-C', repo_path,
        'show', f'{commit_hash}:{file_path}'
    ]
    result = subprocess.run(cmd, capture_output=True, check=True)
    
    with open(output_path, 'wb') as f:
        f.write(result.stdout)


def batch_convert_bpmn_to_svg(bpmn_svg_pairs, batch_size=50):
    """
    Convert multiple BPMN files to SVG using batched bpmn-to-image calls.
    
    Processes files in batches to balance performance (fewer browser launches)
    with safety (memory limits, command line length, failure recovery).
    
    Args:
        bpmn_svg_pairs: List of (bpmn_path, svg_path) tuples
        batch_size: Number of files per batch (default 50)
    
    Returns:
        Number of successfully converted files
    """
    if not bpmn_svg_pairs:
        return 0
    
    total = len(bpmn_svg_pairs)
    success_count = 0
    
    # Process in batches
    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch = bpmn_svg_pairs[batch_start:batch_end]
        batch_num = (batch_start // batch_size) + 1
        total_batches = (total + batch_size - 1) // batch_size
        
        batch_start_time = time.time()
        
        # Build command with all file pairs in this batch
        cmd = ['bpmn-to-image', '--no-footer']
        for bpmn_path, svg_path in batch:
            cmd.append(f'{bpmn_path}:{svg_path}')
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            success_count += len(batch)
            elapsed = time.time() - batch_start_time
            print(f"  Batch {batch_num}/{total_batches}: converted {len(batch)} files in {elapsed:.1f}s")
        except subprocess.CalledProcessError as e:
            elapsed = time.time() - batch_start_time
            print(f"  Error in batch {batch_num} after {elapsed:.1f}s: {e}")
            # Count which files in this batch succeeded
            batch_success = sum(1 for _, svg_path in batch if os.path.exists(svg_path))
            success_count += batch_success
            print(f"  Partial success: {batch_success}/{len(batch)} files in batch")
    
    return success_count


def svg_to_png(svg_path, output_path, canvas_width=1920, canvas_height=1080, background='white',
               overlay_text=None):
    """
    Convert SVG to PNG at a fixed canvas size, centering the diagram.
    Uses a two-step process: rsvg-convert for SVG rendering, then ffmpeg to pad/center.
    
    Args:
        svg_path: Path to the SVG file
        output_path: Path for the output PNG
        canvas_width: Fixed canvas width (default 1920 for 1080p)
        canvas_height: Fixed canvas height (default 1080 for 1080p)
        background: Background color (default white)
        overlay_text: Optional text to overlay on the frame (e.g., commit date and message)
    """
    try:
        # Step 1: Render SVG to PNG, fitting within canvas while keeping aspect ratio
        temp_png = output_path + '.temp.png'
        cmd_rsvg = [
            'rsvg-convert',
            '-w', str(canvas_width),
            '-h', str(canvas_height),
            '--keep-aspect-ratio',
            '--background-color', background,
            '-o', temp_png,
            svg_path
        ]
        subprocess.run(cmd_rsvg, check=True, capture_output=True)
        
        # Step 2: Use ffmpeg to pad the image to exact canvas size, centering it
        # Optionally add text overlay with commit info
        vf_filters = [f'pad={canvas_width}:{canvas_height}:(ow-iw)/2:(oh-ih)/2:white']
        
        if overlay_text:
            # Escape special characters for ffmpeg drawtext
            escaped_text = overlay_text.replace("'", "'\\''").replace(':', '\\:')
            # Add semi-transparent background box, white text, top-left position
            vf_filters.append(
                f"drawtext=text='{escaped_text}':fontsize=24:fontcolor=white:"
                f"x=20:y=20:box=1:boxcolor=black@0.4:boxborderw=10"
            )
        
        cmd_ffmpeg = [
            'ffmpeg', '-y',
            '-i', temp_png,
            '-vf', ','.join(vf_filters),
            output_path
        ]
        subprocess.run(cmd_ffmpeg, check=True, capture_output=True)
        
        # Clean up temp file
        os.remove(temp_png)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error converting SVG {svg_path}: {e}")
        # Clean up temp file if it exists
        if os.path.exists(output_path + '.temp.png'):
            os.remove(output_path + '.temp.png')
        return False
    except FileNotFoundError as e:
        print(f"Error: Required tool not found. Install with: brew install librsvg ffmpeg")
        return False


def get_audio_duration(audio_path):
    """Get the duration of an audio file in seconds using ffprobe."""
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        audio_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"Error getting audio duration: {e}")
        return None


def create_timelapse_video(image_dir, output_video, fps=2, audio_path=None):
    """Create a video from a sequence of images using ffmpeg, optionally with audio."""
    # Get all PNG files sorted by name (they're numbered sequentially)
    images = sorted(Path(image_dir).glob('*.png'))
    
    if not images:
        print("No images found for timelapse")
        return False
    
    print(f"Creating timelapse from {len(images)} images at {fps:.2f} fps...")
    
    # Build ffmpeg command
    cmd = [
        'ffmpeg', '-y',
        '-framerate', str(fps),
        '-pattern_type', 'glob',
        '-i', os.path.join(image_dir, '*.png'),
    ]
    
    # Add audio input if provided
    if audio_path:
        cmd.extend(['-i', audio_path])
    
    cmd.extend([
        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p',
        '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2',  # Ensure even dimensions
    ])
    
    # Add audio codec if audio provided
    if audio_path:
        cmd.extend(['-c:a', 'aac', '-shortest'])
    
    cmd.append(output_video)
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"Timelapse saved to: {output_video}")
        
        # Clean up frame images
        print(f"Cleaning up frame images...")
        shutil.rmtree(image_dir)
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error creating video: {e.stderr.decode()}")
        return False


def generate_timelapse(repo_path, filename, output_video=None, since=None, until=None, 
                       canvas_width=1920, canvas_height=1080, batch_size=50, fps=5,
                       show_overlay=True, audio_path=None):
    """
    Generate a timelapse video from git history of a BPMN file.
    
    Uses a four-phase approach:
    1. Extract all BPMN versions from git history
    2. Batch convert BPMNs to SVGs (minimizes browser launches)
    3. Convert SVGs to PNGs at fixed canvas size
    4. Create timelapse video from PNGs
    
    Args:
        repo_path: Path to the git repository root
        filename: Name of the BPMN file to track
        output_video: Output video path (default: <filename>_timelapse.mp4)
        since: Optional start date (YYYY-MM-DD)
        until: Optional end date (YYYY-MM-DD)
        canvas_width: Fixed canvas width for output images
        canvas_height: Fixed canvas height for output images
        batch_size: Number of files per BPMN->SVG batch (default 50)
        fps: Frames per second for output video (default 5)
        show_overlay: Whether to show commit date/message overlay (default True)
        audio_path: Optional path to audio file (syncs video length to audio)
    """
    # Generate default output filename from BPMN filename
    base_name = os.path.splitext(filename)[0]
    if output_video is None:
        output_video = f"{base_name}_timelapse.mp4"
    
    # All output goes into ./output directory
    repo_path = os.path.abspath(repo_path)
    output_base = os.path.abspath('./output')
    output_dir = os.path.join(output_base, 'frames')
    output_video = os.path.join(output_base, output_video)
    svg_dir = os.path.join(output_dir, 'svg')
    bpmn_dir = os.path.join(output_dir, 'bpmn')
    
    # Clean up any existing output directory
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    
    # Create output directories
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(svg_dir, exist_ok=True)
    os.makedirs(bpmn_dir, exist_ok=True)
    print(f"Images will be saved to: {output_dir}")
    print(f"Canvas size: {canvas_width}x{canvas_height}")
    
    # Get all commits that modified the file
    print(f"Finding commits for {filename}...")
    commits = get_commits_for_file(repo_path, filename, since, until)
    
    if not commits:
        print(f"No commits found for {filename}")
        return
    
    print(f"Found {len(commits)} commits")
    
    total_start_time = time.time()
    
    # Phase 1: Extract all BPMN versions from git
    phase1_start = time.time()
    print(f"\n[Phase 1/3] Extracting BPMN files from git history...")
    bpmn_svg_pairs = []
    frame_mapping = []  # Track (frame_num, bpmn_path, svg_path, timestamp, message) for phase 3
    
    for i, (commit_hash, timestamp, message, file_path) in enumerate(commits, 1):
        # Extract BPMN to temp location
        bpmn_path = os.path.join(bpmn_dir, f'frame_{i:04d}.bpmn')
        svg_path = os.path.join(svg_dir, f'frame_{i:04d}.svg')
        
        checkout_file_version(repo_path, commit_hash, file_path, bpmn_path)
        bpmn_svg_pairs.append((bpmn_path, svg_path))
        frame_mapping.append((i, bpmn_path, svg_path, timestamp, message))
        
        if i % 100 == 0 or i == len(commits):
            print(f"  Extracted {i}/{len(commits)} files...")
    
    phase1_elapsed = time.time() - phase1_start
    print(f"  Extracted {len(bpmn_svg_pairs)} BPMN files in {phase1_elapsed:.1f}s")
    
    # Phase 2: Batch convert BPMN to SVG
    phase2_start = time.time()
    print(f"\n[Phase 2/3] Converting BPMN to SVG (batch size: {batch_size})...")
    svg_count = batch_convert_bpmn_to_svg(bpmn_svg_pairs, batch_size=batch_size)
    phase2_elapsed = time.time() - phase2_start
    print(f"  Converted {svg_count}/{len(bpmn_svg_pairs)} files to SVG in {phase2_elapsed:.1f}s")
    
    # Phase 3: Convert SVGs to PNGs at fixed canvas size
    phase3_start = time.time()
    print(f"\n[Phase 3/3] Converting SVGs to PNG ({canvas_width}x{canvas_height})...")
    png_count = 0
    total_files = len(frame_mapping)
    for i, (frame_num, bpmn_path, svg_path, timestamp, message) in enumerate(frame_mapping, 1):
        if not os.path.exists(svg_path):
            continue
        
        # Format overlay text with date and commit message
        overlay_text = None
        if show_overlay:
            date_str = datetime.fromtimestamp(timestamp).strftime('%Y %B %d')
            # Truncate long messages
            short_message = message[:80] + '...' if len(message) > 80 else message
            overlay_text = f"{date_str} | {short_message}"
        
        output_image = os.path.join(output_dir, f'frame_{frame_num:04d}.png')
        if svg_to_png(svg_path, output_image, canvas_width, canvas_height, overlay_text=overlay_text):
            png_count += 1
        
        # Update progress on same line
        elapsed = time.time() - phase3_start
        print(f"\r  Converting: {i}/{total_files} ({elapsed:.1f}s)", end='', flush=True)
    
    phase3_elapsed = time.time() - phase3_start
    print(f"\r  Converted {png_count}/{total_files} to PNG in {phase3_elapsed:.1f}s")
    
    # Clean up temporary files
    print(f"\nCleaning up temporary files...")
    shutil.rmtree(bpmn_dir)
    shutil.rmtree(svg_dir)
    
    # Phase 4: Create timelapse video
    phase4_start = time.time()
    
    # If audio provided, calculate FPS to sync video length to audio
    if audio_path:
        audio_duration = get_audio_duration(audio_path)
        if audio_duration:
            fps = png_count / audio_duration
            print(f"\n[Phase 4/4] Creating timelapse video with audio...")
            print(f"  Audio: {audio_path}")
            print(f"  Audio duration: {audio_duration:.1f}s")
            print(f"  Calculated FPS: {fps:.2f} ({png_count} frames / {audio_duration:.1f}s)")
            if fps < 1:
                print(f"  Warning: Low FPS ({fps:.2f}) - video will play slowly")
        else:
            print(f"\n[Phase 4/4] Creating timelapse video (audio duration detection failed)...")
            audio_path = None  # Fall back to no audio
    else:
        print(f"\n[Phase 4/4] Creating timelapse video at {fps} fps...")
    
    create_timelapse_video(output_dir, output_video, fps, audio_path)
    phase4_elapsed = time.time() - phase4_start
    
    total_elapsed = time.time() - total_start_time
    print(f"\nDone! Video saved to: {output_video}")
    print(f"Total time: {total_elapsed:.1f}s (Phase 1: {phase1_elapsed:.1f}s, Phase 2: {phase2_elapsed:.1f}s, Phase 3: {phase3_elapsed:.1f}s, Phase 4: {phase4_elapsed:.1f}s)")


def main():
    parser = argparse.ArgumentParser(
        description='Generate a timelapse video from git history of a BPMN file'
    )
    
    parser.add_argument('filename', help='Name of the BPMN file to track')
    parser.add_argument('repo_path', help='Path to the git repository root')
    parser.add_argument('-o', '--output', help='Output video file (default: <filename>_timelapse.mp4)')
    parser.add_argument('--since', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--until', help='End date (YYYY-MM-DD)')
    parser.add_argument('--width', type=int, default=1920, help='Canvas width (default: 1920)')
    parser.add_argument('--height', type=int, default=1080, help='Canvas height (default: 1080)')
    parser.add_argument('--batch-size', type=int, default=50, help='Batch size (default: 50)')
    parser.add_argument('--fps', type=int, default=5, help='Frames per second (default: 5, ignored if --audio provided)')
    parser.add_argument('--no-overlay', action='store_true', help='Disable commit info overlay')
    parser.add_argument('--audio', help='Path to audio file (syncs video length to audio duration)')
    
    args = parser.parse_args()
    
    generate_timelapse(
        repo_path=args.repo_path,
        filename=args.filename,
        output_video=args.output,
        since=args.since,
        until=args.until,
        canvas_width=args.width,
        canvas_height=args.height,
        batch_size=args.batch_size,
        fps=args.fps,
        show_overlay=not args.no_overlay,
        audio_path=args.audio
    )


if __name__ == '__main__':
    main()
