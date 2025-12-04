import os
import argparse
import subprocess
import tempfile
import shutil
from datetime import datetime
from pathlib import Path


def get_commits_for_file(repo_path, filename, since=None, until=None):
    """
    Get all commits on main branch that modified the specified file.
    Returns list of (commit_hash, timestamp, commit_message) tuples, oldest first.
    """
    cmd = [
        'git', '-C', repo_path,
        'log', '--follow', '--format=%H %at %s',
        '--first-parent', 'main',  # Only main branch
        '--', f'**/{filename}'  # Match file anywhere in repo
    ]
    
    if since:
        cmd.insert(4, f'--since={since}')
    if until:
        cmd.insert(4, f'--until={until}')
    
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    
    commits = []
    for line in result.stdout.strip().split('\n'):
        if line:
            parts = line.split(' ', 2)
            if len(parts) >= 2:
                commit_hash = parts[0]
                timestamp = int(parts[1])
                message = parts[2] if len(parts) > 2 else ''
                commits.append((commit_hash, timestamp, message))
    
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


def convert_bpmn_to_svg(bpmn_path, output_path):
    """Convert a single BPMN file to SVG using bpmn-to-image."""
    try:
        cmd = ['bpmn-to-image', '--no-footer', bpmn_path + ':' + output_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error converting {bpmn_path}: {e}")
        return False


def svg_to_png(svg_path, output_path, canvas_width=1920, canvas_height=1080, background='white'):
    """
    Convert SVG to PNG at a fixed canvas size, centering the diagram.
    Uses a two-step process: rsvg-convert for SVG rendering, then ffmpeg to pad/center.
    
    Args:
        svg_path: Path to the SVG file
        output_path: Path for the output PNG
        canvas_width: Fixed canvas width (default 1920 for 1080p)
        canvas_height: Fixed canvas height (default 1080 for 1080p)
        background: Background color (default white)
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
        cmd_ffmpeg = [
            'ffmpeg', '-y',
            '-i', temp_png,
            '-vf', f'pad={canvas_width}:{canvas_height}:(ow-iw)/2:(oh-ih)/2:white',
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


def create_timelapse_video(image_dir, output_video, fps=2):
    """Create a video from a sequence of images using ffmpeg."""
    # Get all PNG files sorted by name (they're numbered sequentially)
    images = sorted(Path(image_dir).glob('*.png'))
    
    if not images:
        print("No images found for timelapse")
        return False
    
    print(f"Creating timelapse from {len(images)} images...")
    
    # Use ffmpeg to create video
    cmd = [
        'ffmpeg', '-y',
        '-framerate', str(fps),
        '-pattern_type', 'glob',
        '-i', os.path.join(image_dir, '*.png'),
        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p',
        '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2',  # Ensure even dimensions
        output_video
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"Timelapse saved to: {output_video}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error creating video: {e.stderr.decode()}")
        return False


def generate_images(repo_path, filename, output_dir, since=None, until=None, 
                    canvas_width=1920, canvas_height=1080):
    """
    Step 1: Generate images from git history of a BPMN file.
    
    Args:
        repo_path: Path to the git repository root
        filename: Name of the BPMN file to track
        output_dir: Directory to save the generated images
        since: Optional start date (YYYY-MM-DD)
        until: Optional end date (YYYY-MM-DD)
        canvas_width: Fixed canvas width for output images
        canvas_height: Fixed canvas height for output images
    """
    repo_path = os.path.abspath(repo_path)
    output_dir = os.path.abspath(output_dir)
    svg_dir = os.path.join(output_dir, 'svg')
    
    # Create output directories
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(svg_dir, exist_ok=True)
    print(f"Images will be saved to: {output_dir}")
    print(f"Canvas size: {canvas_width}x{canvas_height}")
    
    # Get all commits that modified the file
    print(f"Finding commits for {filename}...")
    commits = get_commits_for_file(repo_path, filename, since, until)
    
    if not commits:
        print(f"No commits found for {filename}")
        return
    
    print(f"Found {len(commits)} commits")
    
    # Process each commit
    for i, (commit_hash, timestamp, message) in enumerate(commits, 1):
        date_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
        print(f"[{i}/{len(commits)}] {date_str} - {commit_hash[:8]} - {message[:50]}")
        
        # Find the file path at this commit
        file_path = get_file_path_at_commit(repo_path, commit_hash, filename)
        if not file_path:
            print(f"  File not found at commit {commit_hash[:8]}, skipping")
            continue
        
        # Checkout the file to a temp location
        temp_bpmn = os.path.join(output_dir, f'temp_{i:04d}.bpmn')
        checkout_file_version(repo_path, commit_hash, file_path, temp_bpmn)
        
        # Convert BPMN to SVG
        svg_path = os.path.join(svg_dir, f'frame_{i:04d}.svg')
        if not convert_bpmn_to_svg(temp_bpmn, svg_path):
            os.remove(temp_bpmn)
            continue
        
        # Convert SVG to PNG at fixed canvas size
        output_image = os.path.join(output_dir, f'frame_{i:04d}.png')
        if svg_to_png(svg_path, output_image, canvas_width, canvas_height):
            print(f"  Converted to {output_image}")
        
        # Clean up temp bpmn file
        os.remove(temp_bpmn)
    
    print(f"\nDone! {len(commits)} images saved to: {output_dir}")
    print(f"SVGs preserved in: {svg_dir}")
    print("Review the images, then run 'video' command to generate the timelapse.")


def main():
    parser = argparse.ArgumentParser(
        description='Generate a timelapse video from git history of a BPMN file'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Step 1: Generate images
    gen_parser = subparsers.add_parser('generate', help='Generate images from git history')
    gen_parser.add_argument('filename', help='Name of the BPMN file to track')
    gen_parser.add_argument('repo_path', help='Path to the git repository root')
    gen_parser.add_argument('-o', '--output-dir', default='./timelapse_frames',
                            help='Output directory for images (default: ./timelapse_frames)')
    gen_parser.add_argument('--since', help='Start date (YYYY-MM-DD)')
    gen_parser.add_argument('--until', help='End date (YYYY-MM-DD)')
    gen_parser.add_argument('--width', type=int, default=1920,
                            help='Canvas width in pixels (default: 1920)')
    gen_parser.add_argument('--height', type=int, default=1080,
                            help='Canvas height in pixels (default: 1080)')
    
    # Step 2: Create video
    video_parser = subparsers.add_parser('video', help='Create video from generated images')
    video_parser.add_argument('image_dir', help='Directory containing the generated images')
    video_parser.add_argument('-o', '--output', default='timelapse.mp4',
                              help='Output video file path (default: timelapse.mp4)')
    video_parser.add_argument('--fps', type=int, default=2,
                              help='Frames per second (default: 2)')
    
    args = parser.parse_args()
    
    if args.command == 'generate':
        generate_images(
            repo_path=args.repo_path,
            filename=args.filename,
            output_dir=args.output_dir,
            since=args.since,
            until=args.until,
            canvas_width=args.width,
            canvas_height=args.height
        )
    elif args.command == 'video':
        create_timelapse_video(
            image_dir=args.image_dir,
            output_video=args.output,
            fps=args.fps
        )
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
