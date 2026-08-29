"""Vertical 9:16 Shorts / Reels generator with animated karaoke-style subtitles."""

import math
import subprocess
from pathlib import Path
from typing import List, Optional
from rich.console import Console

from adn.config import settings
from adn.cutter import sanitize_filename
from adn.models import ShortCandidate, Transcript

console = Console()


def format_ass_timestamp(seconds: float) -> str:
    """Format seconds into ASS timestamp format: H:MM:SS.cs"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def generate_karaoke_ass(
    transcript: Transcript,
    start_time: float,
    end_time: float,
    output_ass: Path
) -> Path:
    """Generate an Advanced SubStation Alpha (.ass) subtitle file with word-by-word highlight."""
    output_ass.parent.mkdir(parents=True, exist_ok=True)

    # ASS Header with high-impact Short / TikTok typography styling
    # Font: Arial / Helvetica / Impact / Montserrat, Size: 48, Bold, Border: 4, Active Yellow Highlight
    ass_content = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        # PrimaryColour: &H00FFFFFF (White), Outline: &H00000000 (Black), Yellow Highlight: &H0000E6FF
        "Style: Default,Arial Black,58,&H00FFFFFF,&H0000E6FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60,480,1",
        "Style: Highlight,Arial Black,58,&H0000E6FF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60,480,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    # Find words falling inside [start_time, end_time]
    active_words = []
    for seg in transcript.segments:
        if seg.words:
            for w in seg.words:
                if w.end >= start_time and w.start <= end_time:
                    active_words.append(w)
        elif seg.end >= start_time and seg.start <= end_time:
            # Fallback if segment has no word timestamps
            words_in_seg = seg.text.split()
            seg_dur = max(0.1, seg.end - seg.start)
            word_dur = seg_dur / max(1, len(words_in_seg))
            for idx, text_w in enumerate(words_in_seg):
                w_start = seg.start + idx * word_dur
                w_end = w_start + word_dur
                if w_end >= start_time and w_start <= end_time:
                    active_words.append(type("Word", (), {"word": text_w, "start": w_start, "end": w_end})())

    if not active_words:
        # If no words found, write a minimal blank ASS
        with open(output_ass, "w", encoding="utf-8") as f:
            f.write("\n".join(ass_content))
        return output_ass

    # Group into short 3-5 word subtitle chunks for fast reading
    chunk_size = 4
    for i in range(0, len(active_words), chunk_size):
        chunk = active_words[i:i + chunk_size]
        chunk_start = max(0.0, chunk[0].start - start_time)
        chunk_end = max(chunk_start + 0.5, chunk[-1].end - start_time)

        # Build karaoke / highlighted line
        line_text_parts = []
        for w in chunk:
            dur_cs = int(max(10, (w.end - w.start) * 100))
            clean_w = w.word.strip().upper()
            line_text_parts.append(f"{{\\k{dur_cs}}}{clean_w}")

        dialogue_line = (
            f"Dialogue: 0,{format_ass_timestamp(chunk_start)},{format_ass_timestamp(chunk_end)},"
            f"Default,,0,0,0,,{' '.join(line_text_parts)}"
        )
        ass_content.append(dialogue_line)

    with open(output_ass, "w", encoding="utf-8") as f:
        f.write("\n".join(ass_content))

    return output_ass


def render_short_video(
    input_video: Path,
    output_short: Path,
    start_seconds: float,
    end_seconds: float,
    ass_subtitle_path: Optional[Path] = None,
) -> Path:
    """Crop 16:9 to 9:16 vertical video and burn animated subtitles."""
    ffmpeg = settings.ffmpeg_path
    if not ffmpeg:
        raise RuntimeError("FFmpeg is missing.")

    output_short.parent.mkdir(parents=True, exist_ok=True)
    duration = end_seconds - start_seconds

    # Video filter chain: Center crop to 9:16 (1080x1920) + Burn ASS Subtitles
    # crop=ih*(9/16):ih, scale=1080:1920
    vf_filters = [
        "crop=ih*(9/16):ih",
        "scale=1080:1920:flags=lanczos",
    ]

    if ass_subtitle_path and ass_subtitle_path.exists():
        # Escape path for FFmpeg subtitles filter
        escaped_ass = str(ass_subtitle_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        vf_filters.append(f"ass='{escaped_ass}'")

    filter_complex = ",".join(vf_filters)

    cmd = [
        ffmpeg,
        "-y",
        "-ss", f"{start_seconds:.3f}",
        "-i", str(input_video),
        "-t", f"{duration:.3f}",
        "-vf", filter_complex,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_short)
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to generate vertical short:\n{result.stderr}")

    return output_short


def generate_all_shorts(
    input_video: Path,
    transcript: Transcript,
    shorts: List[ShortCandidate],
    output_dir: Path
) -> List[Path]:
    """Batch generate vertical shorts with burned subtitles."""
    shorts_dir = output_dir / "shorts"
    shorts_dir.mkdir(parents=True, exist_ok=True)

    generated_shorts = []
    console.print(f"[cyan]Generating {len(shorts)} vertical shorts (9:16 with animated subtitles)...[/cyan]")

    for idx, short in enumerate(shorts, start=1):
        clean_title = sanitize_filename(short.title)
        short_filename = f"short_{idx:02d}_{clean_title}.mp4"
        ass_filename = f"short_{idx:02d}_{clean_title}.ass"

        short_path = shorts_dir / short_filename
        ass_path = shorts_dir / ass_filename

        console.print(f"  [{idx}/{len(shorts)}] Rendering '{short.title}' ({short.duration_seconds:.1f}s)...")
        try:
            # 1. Generate karaoke ASS
            generate_karaoke_ass(
                transcript=transcript,
                start_time=short.start_seconds,
                end_time=short.end_seconds,
                output_ass=ass_path,
            )

            # 2. Render vertical video
            render_short_video(
                input_video=input_video,
                output_short=short_path,
                start_seconds=short.start_seconds,
                end_seconds=short.end_seconds,
                ass_subtitle_path=ass_path,
            )
            generated_shorts.append(short_path)
            console.print(f"  [green]✓ Created Short:[/green] {short_filename}")
        except Exception as e:
            console.print(f"  [red]✗ Error creating short {short_filename}:[/red] {e}")

    return generated_shorts
