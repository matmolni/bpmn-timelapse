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


def convert_bpmn_to_image(bpmn_path, output_path, scale=0.5):
    """Convert a single BPMN file to PNG using bpmn-to-image.
    
    Args:
        bpmn_path: Path to the BPMN file
        output_path: Path for the output image
        scale: Scale factor (default 0.5 = half size, reduces 32k to 16k)
    """
    try:
        cmd = ['bpmn-to-image', f'--scale={scale}', bpmn_path + ':' + output_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error converting {bpmn_path}: {e}")
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


def generate_images(repo_path, filename, output_dir, since=None, until=None, scale=0.5):
    """
    Step 1: Generate images from git history of a BPMN file.
    
    Args:
        repo_path: Path to the git repository root
        filename: Name of the BPMN file to track
        output_dir: Directory to save the generated images
        since: Optional start date (YYYY-MM-DD)
        until: Optional end date (YYYY-MM-DD)
        scale: Scale factor for images (default 0.5)
    """
    repo_path = os.path.abspath(repo_path)
    output_dir = os.path.abspath(output_dir)
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    print(f"Images will be saved to: {output_dir}")
    
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
        
        # Convert to image
        output_image = os.path.join(output_dir, f'frame_{i:04d}.png')
        if convert_bpmn_to_image(temp_bpmn, output_image, scale=scale):
            print(f"  Converted to {output_image}")
        
        # Clean up temp bpmn file
        os.remove(temp_bpmn)
    
    print(f"\nDone! {len(commits)} images saved to: {output_dir}")
    print("Review the images, then run with --create-video to generate the timelapse.")


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
    gen_parser.add_argument('--scale', type=float, default=0.5,
                            help='Scale factor for images (default: 0.5, use 0.25 for very large diagrams)')
    
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
            scale=args.scale
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
