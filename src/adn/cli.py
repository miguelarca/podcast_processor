"""Unified CLI entrypoint for ADN Divergente podcast processor."""

import json
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from adn.analyzer import run_analysis
from adn.config import settings
from adn.cutter import cut_all_clips
from adn.models import EpisodeAnalysis, Transcript
from adn.shorts import generate_all_shorts
from adn.transcriber import run_transcription

app = typer.Typer(
    name="adn",
    help="⚡ ADN Divergente: AI-Powered Podcast Post-Production CLI",
    add_completion=False,
)
console = Console()


def _display_analysis_summary(analysis: EpisodeAnalysis):
    """Render a beautiful terminal summary of the analysis."""
    console.print("\n" + "=" * 60)
    console.print(Panel(f"[bold white]{analysis.episode_summary}[/bold white]", title="🎙️ Resumen del Episodio", border_style="cyan"))

    # Titles Table
    table_titles = Table(title="🎯 Opciones de Títulos para YouTube", border_style="green")
    table_titles.add_column("Estilo", style="cyan", width=12)
    table_titles.add_column("Título", style="bold yellow")
    table_titles.add_column("Estrategia", style="dim")
    for t in analysis.title_options:
        table_titles.add_row(t.style.upper(), t.title, t.rationale)
    console.print(table_titles)

    # Chapters Table
    table_chapters = Table(title="⏱️ Capítulos / Timestamps de YouTube", border_style="blue")
    table_chapters.add_column("Tiempo", style="bold magenta", width=10)
    table_chapters.add_column("Capítulo", style="white")
    for ch in analysis.youtube_chapters:
        table_chapters.add_row(ch.timestamp, ch.title)
    console.print(table_chapters)

    # Clips Table
    table_clips = Table(title="✂️ Clips / Mini-Episodios Recomendados (16:9)", border_style="yellow")
    table_clips.add_column("ID", style="dim", width=8)
    table_clips.add_column("Título del Clip", style="bold")
    table_clips.add_column("Duración", style="green", width=10)
    table_clips.add_column("Hook / Tema", style="white")
    for c in analysis.clips:
        table_clips.add_row(c.id, c.title, c.duration_formatted, c.hook)
    console.print(table_clips)

    # Shorts Table
    table_shorts = Table(title="📱 Shorts / Reels / TikTok (9:16)", border_style="magenta")
    table_shorts.add_column("ID", style="dim", width=8)
    table_shorts.add_column("Título", style="bold")
    table_shorts.add_column("Duración", style="green", width=10)
    table_shorts.add_column("Cita Gancho", style="white")
    for s in analysis.shorts:
        table_shorts.add_row(s.id, s.title, f"{s.duration_seconds:.1f}s", s.hook_quote)
    console.print(table_shorts)


def _handle_error(err: Exception):
    """Render a clean, user-friendly error panel instead of an unformatted traceback."""
    console.print()
    err_msg = str(err).strip()

    # Detect common causes to give helpful hints
    hint = "Check your configuration with [bold cyan]adn doctor[/bold cyan]."
    if "API_KEY" in err_msg or "401" in err_msg or "UNAUTHENTICATED" in err_msg:
        hint = "Verify that your API keys are correctly set in the [bold].env[/bold] file."
    elif "503" in err_msg or "UNAVAILABLE" in err_msg:
        hint = "The AI service is experiencing a temporary spike in traffic. Wait a moment and try again."
    elif "FFmpeg" in err_msg:
        hint = "Make sure FFmpeg is installed via Homebrew: [bold cyan]brew install ffmpeg[/bold cyan]."

    console.print(
        Panel(
            f"[bold red]❌ Error:[/bold red] {err_msg}\n\n[dim]💡 Tip: {hint}[/dim]",
            title="⚠️ ADN Divergente Pipeline Notice",
            border_style="red",
        )
    )
    raise typer.Exit(code=1)


def resolve_output_dir(media_path: Path, custom_output: Optional[Path] = None) -> Path:
    """Resolve target output folder: custom output, or folder alongside the source media."""
    if custom_output:
        return custom_output
    # If media is in current workspace directory, use ./output/<name>, otherwise use <media_parent>/<name>
    try:
        if media_path.resolve().parent == Path.cwd().resolve():
            return Path.cwd() / "output" / media_path.stem
    except Exception:
        pass
    return media_path.parent / media_path.stem


@app.command()
def process(
    media_file: Path = typer.Argument(..., help="Path to raw Riverside recording (.mp4, .mov, .wav, etc.)"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Custom output directory"),
    backend: Optional[str] = typer.Option(None, "--whisper-backend", "-w", help="Transcription backend: faster-whisper | groq"),
    provider: Optional[str] = typer.Option(None, "--llm-provider", "-p", help="LLM provider: gemini | openai"),
    skip_cuts: bool = typer.Option(False, "--skip-cuts", help="Skip cutting 16:9 video clips"),
    skip_shorts: bool = typer.Option(False, "--skip-shorts", help="Skip generating 9:16 vertical shorts"),
):
    """🚀 Run the full pipeline: Transcribe -> Analyze -> Generate Metadata -> Cut Clips -> Generate Shorts."""
    try:
        if not media_file.exists():
            console.print(f"[red]Error: Media file not found:[/red] {media_file}")
            raise typer.Exit(1)

        base_name = media_file.stem
        target_out_dir = resolve_output_dir(media_file, output_dir)
        target_out_dir.mkdir(parents=True, exist_ok=True)

        console.print(Panel(f"[bold cyan]Processing Episode:[/bold cyan] {media_file.name}\n[bold]Output Directory:[/bold] {target_out_dir}", title="ADN Divergente Processor"))

        # Step 1: Transcribe
        transcript = run_transcription(input_file=media_file, output_dir=target_out_dir, backend=backend)

        # Step 2: Analyze
        analysis = run_analysis(transcript=transcript, output_dir=target_out_dir, base_name=base_name, provider=provider)

        # Render summary in terminal
        _display_analysis_summary(analysis)

        # Step 3: Cut 16:9 Clips
        if not skip_cuts and media_file.suffix.lower() in [".mp4", ".mov", ".mkv", ".webm"]:
            console.print("\n[bold cyan]Cutting candidate clips (16:9)...[/bold cyan]")
            cut_all_clips(input_video=media_file, clips=analysis.clips, output_dir=target_out_dir)

        # Step 4: Generate 9:16 Shorts with Subtitles
        if not skip_shorts and media_file.suffix.lower() in [".mp4", ".mov", ".mkv", ".webm"]:
            console.print("\n[bold magenta]Generating candidate shorts (9:16 + subtitles)...[/bold magenta]")
            generate_all_shorts(input_video=media_file, transcript=transcript, shorts=analysis.shorts, output_dir=target_out_dir)

        console.print(f"\n[bold green]✨ Processing complete![/bold green] All files saved in: {target_out_dir}\n")
    except Exception as e:
        _handle_error(e)


@app.command()
def transcribe(
    media_file: Path = typer.Argument(..., help="Path to video or audio file"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o"),
    backend: Optional[str] = typer.Option(None, "--backend", "-b", help="faster-whisper | groq"),
):
    """📝 Transcribe audio/video to JSON, TXT, and SRT subtitles."""
    try:
        target_out_dir = resolve_output_dir(media_file, output_dir)
        transcript = run_transcription(input_file=media_file, output_dir=target_out_dir, backend=backend)
        console.print(f"[green]Transcription finished ({transcript.duration / 60:.1f} minutes).[/green]")
    except Exception as e:
        _handle_error(e)


@app.command()
def analyze(
    transcript_file: Path = typer.Argument(..., help="Path to transcript.json"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="gemini | openai"),
):
    """🧠 Generate titles, chapters, description, and clip candidates from an existing transcript."""
    try:
        if not transcript_file.exists():
            console.print(f"[red]Error:[/red] File not found {transcript_file}")
            raise typer.Exit(1)

        with open(transcript_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            transcript = Transcript(**data)

        target_out_dir = output_dir or transcript_file.parent
        base_name = transcript_file.stem.replace("_transcript", "")
        analysis = run_analysis(transcript=transcript, output_dir=target_out_dir, base_name=base_name, provider=provider)
        _display_analysis_summary(analysis)
    except Exception as e:
        _handle_error(e)


@app.command()
def cut(
    video_file: Path = typer.Argument(..., help="Path to source video file"),
    analysis_file: Path = typer.Argument(..., help="Path to analysis.json"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o"),
):
    """✂️ Cut 16:9 candidate clips using an existing analysis.json file."""
    try:
        with open(analysis_file, "r", encoding="utf-8") as f:
            analysis = EpisodeAnalysis(**json.load(f))

        target_out_dir = output_dir or analysis_file.parent
        cut_all_clips(input_video=video_file, clips=analysis.clips, output_dir=target_out_dir)
    except Exception as e:
        _handle_error(e)


@app.command()
def shorts(
    video_file: Path = typer.Argument(..., help="Path to source video file"),
    analysis_file: Path = typer.Argument(..., help="Path to analysis.json"),
    transcript_file: Path = typer.Argument(..., help="Path to transcript.json"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o"),
):
    """📱 Generate 9:16 vertical shorts with burned-in dynamic subtitles."""
    try:
        with open(analysis_file, "r", encoding="utf-8") as f:
            analysis = EpisodeAnalysis(**json.load(f))
        with open(transcript_file, "r", encoding="utf-8") as f:
            transcript = Transcript(**json.load(f))

        target_out_dir = output_dir or analysis_file.parent
        generate_all_shorts(input_video=video_file, transcript=transcript, shorts=analysis.shorts, output_dir=target_out_dir)
    except Exception as e:
        _handle_error(e)


@app.command()
def doctor():
    """🩺 Inspect system environment, FFmpeg status, and AI API keys."""
    table = Table(title="ADN Divergente Environment Health Check", border_style="cyan")
    table.add_column("Component", style="bold")
    table.add_column("Status", style="yellow")
    table.add_column("Details", style="dim")

    # Check FFmpeg
    ffmpeg = settings.ffmpeg_path
    if ffmpeg:
        table.add_row("FFmpeg", "[green]✓ Installed[/green]", ffmpeg)
    else:
        table.add_row("FFmpeg", "[red]✗ Missing[/red]", "Run: brew install ffmpeg")

    # Check Gemini API Key
    if settings.GEMINI_API_KEY:
        table.add_row("Gemini API Key", "[green]✓ Configured[/green]", f"{settings.GEMINI_API_KEY[:6]}...")
    else:
        table.add_row("Gemini API Key", "[yellow]○ Not Set[/yellow]", "Add GEMINI_API_KEY in .env")

    # Check OpenAI API Key
    if settings.OPENAI_API_KEY:
        table.add_row("OpenAI API Key", "[green]✓ Configured[/green]", f"{settings.OPENAI_API_KEY[:6]}...")
    else:
        table.add_row("OpenAI API Key", "[yellow]○ Not Set[/yellow]", "Add OPENAI_API_KEY in .env")

    # Check Groq API Key
    if settings.GROQ_API_KEY:
        table.add_row("Groq API Key", "[green]✓ Configured[/green]", f"{settings.GROQ_API_KEY[:6]}...")
    else:
        table.add_row("Groq API Key", "[yellow]○ Not Set[/yellow]", "Add GROQ_API_KEY in .env (optional for fast cloud Whisper)")

    console.print(table)


if __name__ == "__main__":
    app()
