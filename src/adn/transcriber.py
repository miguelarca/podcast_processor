"""Audio extraction and transcription engine supporting faster-whisper and cloud APIs."""

import json
import os
import subprocess
from pathlib import Path
from typing import Optional
from rich.console import Console

from adn.config import settings
from adn.models import Transcript, TranscriptSegment, TranscriptWord

console = Console()


def extract_audio(input_media: Path, output_audio: Path) -> Path:
    """Extract audio from video file to 16kHz mono WAV format."""
    ffmpeg = settings.ffmpeg_path
    if not ffmpeg:
        raise RuntimeError("FFmpeg is not installed or not found in PATH. Install with: brew install ffmpeg")

    output_audio.parent.mkdir(parents=True, exist_ok=True)
    if output_audio.exists():
        console.print(f"[yellow]Audio file already extracted:[/yellow] {output_audio}")
        return output_audio

    cmd = [
        ffmpeg,
        "-y",
        "-i", str(input_media),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(output_audio)
    ]
    console.print(f"[cyan]Extracting audio track from {input_media.name}...[/cyan]")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio extraction failed:\n{result.stderr}")
    return output_audio


def transcribe_faster_whisper(audio_path: Path) -> Transcript:
    """Transcribe audio using local faster-whisper on Mac."""
    from faster_whisper import WhisperModel

    console.print(f"[cyan]Loading faster-whisper model ({settings.WHISPER_MODEL_SIZE})...[/cyan]")
    model = WhisperModel(
        settings.WHISPER_MODEL_SIZE,
        device=settings.WHISPER_DEVICE,
        compute_type=settings.WHISPER_COMPUTE_TYPE
    )

    console.print(f"[cyan]Transcribing {audio_path.name} (Spanish)...[/cyan]")
    segments_gen, info = model.transcribe(
        str(audio_path),
        language="es",
        word_timestamps=True,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )

    segments_list = []
    full_text_chunks = []

    for seg in segments_gen:
        words = []
        if seg.words:
            for w in seg.words:
                words.append(
                    TranscriptWord(
                        word=w.word,
                        start=round(w.start, 2),
                        end=round(w.end, 2),
                        probability=round(w.probability, 3) if hasattr(w, "probability") else None,
                    )
                )

        clean_text = seg.text.strip()
        full_text_chunks.append(clean_text)
        segments_list.append(
            TranscriptSegment(
                id=seg.id,
                start=round(seg.start, 2),
                end=round(seg.end, 2),
                text=clean_text,
                words=words,
            )
        )

    return Transcript(
        language="es",
        duration=round(info.duration, 2),
        full_text=" ".join(full_text_chunks),
        segments=segments_list,
    )


def transcribe_groq(audio_path: Path) -> Transcript:
    """Transcribe audio using Groq cloud API (ultra-fast Whisper)."""
    from groq import Groq

    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not set in .env")

    client = Groq(api_key=settings.GROQ_API_KEY)
    console.print(f"[cyan]Uploading and transcribing via Groq Whisper API...[/cyan]")
    with open(audio_path, "rb") as file:
        response = client.audio.transcriptions.create(
            file=(audio_path.name, file.read()),
            model="whisper-large-v3",
            language="es",
            response_format="verbose_json",
            timestamp_granularities=["segment", "word"],
        )

    # Convert response to our Transcript schema
    segments_list = []
    for idx, seg in enumerate(getattr(response, "segments", [])):
        seg_dict = seg if isinstance(seg, dict) else seg.__dict__
        segments_list.append(
            TranscriptSegment(
                id=idx,
                start=round(seg_dict.get("start", 0.0), 2),
                end=round(seg_dict.get("end", 0.0), 2),
                text=seg_dict.get("text", "").strip(),
            )
        )

    return Transcript(
        language="es",
        duration=round(getattr(response, "duration", 0.0), 2),
        full_text=getattr(response, "text", ""),
        segments=segments_list,
    )


def export_transcript_files(transcript: Transcript, output_dir: Path, base_name: str):
    """Save transcript in JSON, SRT, and TXT formats."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{base_name}_transcript.json"
    txt_path = output_dir / f"{base_name}_transcript.txt"
    srt_path = output_dir / f"{base_name}_transcript.srt"

    # Save JSON
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(transcript.model_dump_json(indent=2))

    # Save TXT
    with open(txt_path, "w", encoding="utf-8") as f:
        for seg in transcript.segments:
            timestamp_str = f"[{int(seg.start // 60):02d}:{int(seg.start % 60):02d}]"
            f.write(f"{timestamp_str} {seg.text}\n")

    # Save SRT
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(transcript.segments, start=1):
            s_h, s_m, s_s = int(seg.start // 3600), int((seg.start % 3600) // 60), int(seg.start % 60)
            s_ms = int((seg.start % 1) * 1000)
            e_h, e_m, e_s = int(seg.end // 3600), int((seg.end % 3600) // 60), int(seg.end % 60)
            e_ms = int((seg.end % 1) * 1000)
            f.write(f"{i}\n{s_h:02d}:{s_m:02d}:{s_s:02d},{s_ms:03d} --> {e_h:02d}:{e_m:02d}:{e_s:02d},{e_ms:03d}\n{seg.text}\n\n")

    console.print(f"[green]Saved transcript files to:[/green] {output_dir}")
    return json_path


def run_transcription(
    input_file: Path,
    output_dir: Path,
    backend: Optional[str] = None
) -> Transcript:
    """Master transcription orchestrator."""
    base_name = input_file.stem
    json_path = output_dir / f"{base_name}_transcript.json"

    if json_path.exists():
        console.print(f"[green]Found cached transcript:[/green] {json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return Transcript(**data)

    # If video/audio, extract or prepare audio
    audio_path = output_dir / f"{base_name}_extracted.wav"
    if input_file.suffix.lower() in [".mp4", ".mov", ".mkv", ".webm", ".avi"]:
        audio_path = extract_audio(input_file, audio_path)
    else:
        audio_path = input_file

    chosen_backend = backend or settings.DEFAULT_TRANSCRIPTION_BACKEND
    if chosen_backend == "groq":
        transcript = transcribe_groq(audio_path)
    else:
        transcript = transcribe_faster_whisper(audio_path)

    export_transcript_files(transcript, output_dir, base_name)
    return transcript
