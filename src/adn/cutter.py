"""FFmpeg-based video and audio segment cutter."""

import re
import subprocess
from pathlib import Path
from typing import List, Optional
from rich.console import Console

from adn.config import settings
from adn.models import ClipCandidate

console = Console()


def sanitize_filename(name: str) -> str:
    """Sanitize a string for safe filesystem usage."""
    s = re.sub(r"[^\w\s-]", "", name).strip().lower()
    return re.sub(r"[-\s]+", "_", s)[:60]


def cut_segment(
    input_video: Path,
    output_clip: Path,
    start_seconds: float,
    end_seconds: float,
    reencode: bool = False
) -> Path:
    """Cut a segment from a video file with FFmpeg."""
    ffmpeg = settings.ffmpeg_path
    if not ffmpeg:
        raise RuntimeError("FFmpeg is not installed or not found in PATH. Install with: brew install ffmpeg")

    output_clip.parent.mkdir(parents=True, exist_ok=True)
    if output_clip.exists():
        console.print(f"[yellow]Clip already exists:[/yellow] {output_clip.name}")
        return output_clip

    duration = end_seconds - start_seconds

    if reencode:
        # Re-encode using Apple Silicon hardware acceleration if on macOS
        cmd = [
            ffmpeg,
            "-y",
            "-ss", f"{start_seconds:.3f}",
            "-i", str(input_video),
            "-t", f"{duration:.3f}",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            str(output_clip)
        ]
    else:
        # Fast lossless stream copy
        cmd = [
            ffmpeg,
            "-y",
            "-ss", f"{start_seconds:.3f}",
            "-i", str(input_video),
            "-t", f"{duration:.3f}",
            "-c", "copy",
            str(output_clip)
        ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        if not reencode:
            console.print(f"[yellow]Stream copy failed, retrying with re-encode for {output_clip.name}...[/yellow]")
            return cut_segment(input_video, output_clip, start_seconds, end_seconds, reencode=True)
        else:
            raise RuntimeError(f"FFmpeg cutting failed for {output_clip.name}:\n{result.stderr}")

    return output_clip


def cut_all_clips(
    input_video: Path,
    clips: List[ClipCandidate],
    output_dir: Path
) -> List[Path]:
    """Cut all candidate clips in batch."""
    clips_dir = output_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    generated_clips = []
    console.print(f"[cyan]Cutting {len(clips)} standalone clips...[/cyan]")

    for idx, clip in enumerate(clips, start=1):
        clean_title = sanitize_filename(clip.title)
        filename = f"clip_{idx:02d}_{clean_title}.mp4"
        out_path = clips_dir / filename

        console.print(f"  [{idx}/{len(clips)}] Cutting '{clip.title}' ({clip.duration_formatted})...")
        try:
            cut_segment(
                input_video=input_video,
                output_clip=out_path,
                start_seconds=clip.start_seconds,
                end_seconds=clip.end_seconds,
            )
            generated_clips.append(out_path)
            console.print(f"  [green]✓ Created:[/green] {filename}")
        except Exception as e:
            console.print(f"  [red]✗ Error cutting {filename}:[/red] {e}")

    return generated_clips
