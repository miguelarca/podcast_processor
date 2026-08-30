"""Unified CLI entrypoint for ADN Divergente podcast processor."""

import json
import sys
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

        # Step 5: Generate Thumbnail Concepts and Image Prompts
        console.print("\n[bold cyan]Generating YouTube thumbnail concepts & prompts...[/bold cyan]")
        try:
            from adn.thumbnail import generate_all_thumbnails
            generate_all_thumbnails(analysis=analysis, output_dir=target_out_dir, base_name=base_name)
        except Exception as th_err:
            console.print(f"[yellow]⚠️  Could not generate thumbnail concepts:[/yellow] {th_err}")

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
def upload(
    video_file: Path = typer.Argument(..., help="Path to video file to upload"),
    analysis_file: Path = typer.Argument(..., help="Path to analysis.json with title/chapters metadata"),
    transcript_file: Optional[Path] = typer.Option(None, "--transcript", "-t", help="Path to transcript.srt for native CC captions"),
    title: Optional[str] = typer.Option(None, "--title", help="Custom video title (overrides AI suggestions)"),
    privacy: str = typer.Option("unlisted", "--privacy", "-p", help="unlisted | private | public"),
    thumbnail: Optional[Path] = typer.Option(None, "--thumbnail", help="Path to thumbnail image file (.png/.jpg)"),
):
    """🚀 Upload a full episode or video clip to YouTube with automated metadata & chapters."""
    try:
        from adn.uploader import upload_full_episode

        if not video_file.exists():
            console.print(f"[red]Error: Video file not found:[/red] {video_file}")
            raise typer.Exit(1)
        if not analysis_file.exists():
            console.print(f"[red]Error: Analysis file not found:[/red] {analysis_file}")
            raise typer.Exit(1)

        upload_full_episode(
            video_path=video_file,
            analysis_path=analysis_file,
            transcript_path=transcript_file,
            custom_title=title,
            privacy_status=privacy,
            thumbnail_path=thumbnail,
        )
    except Exception as e:
        _handle_error(e)


@app.command(name="upload-shorts")
def upload_shorts(
    analysis_file: Path = typer.Argument(..., help="Path to analysis.json"),
    shorts_dir: Optional[Path] = typer.Option(None, "--shorts-dir", "-s", help="Custom folder containing shorts/"),
    privacy: str = typer.Option("unlisted", "--privacy", "-p", help="unlisted | private | public"),
):
    """📱 Batch upload all generated vertical shorts to YouTube Shorts."""
    try:
        from adn.uploader import upload_all_shorts_batch

        target_dir = shorts_dir or (analysis_file.parent / "shorts")
        if not target_dir.exists():
            console.print(f"[red]Error: Shorts directory not found:[/red] {target_dir}")
            raise typer.Exit(1)

        upload_all_shorts_batch(
            shorts_dir=target_dir,
            analysis_path=analysis_file,
            privacy_status=privacy,
        )
    except Exception as e:
        _handle_error(e)


@app.command(name="upload-clips")
def upload_clips(
    analysis_file: Path = typer.Argument(..., help="Path to analysis.json"),
    clips_dir: Optional[Path] = typer.Option(None, "--clips-dir", "-c", help="Custom folder containing clips/"),
    privacy: str = typer.Option("unlisted", "--privacy", "-p", help="unlisted | private | public"),
):
    """✂️ Batch upload all generated 16:9 standalone mini-episode clips to YouTube."""
    try:
        from adn.uploader import upload_all_clips_batch

        target_dir = clips_dir or (analysis_file.parent / "clips")
        upload_all_clips_batch(
            clips_dir=target_dir,
            analysis_path=analysis_file,
            privacy_status=privacy,
        )
    except Exception as e:
        _handle_error(e)


@app.command(name="update-metadata")
def update_metadata(
    video_id: str = typer.Argument(..., help="YouTube Video ID (from the URL)"),
    title: str = typer.Option(..., "--title", "-t", help="New title for the video"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="New description for the video"),
):
    """✏️ Update title and description of an existing YouTube video."""
    try:
        from adn.uploader import update_video_metadata
        update_video_metadata(video_id=video_id, title=title, description=description)
    except Exception as e:
        _handle_error(e)


@app.command(name="thumbnail")
def thumbnail_command(
    analysis_file: Path = typer.Argument(..., help="Path to analysis.json"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o"),
    local: bool = typer.Option(True, "--local/--no-local", help="Generate images locally on Apple Silicon GPU using FLUX.1-schnell"),
    count: int = typer.Option(1, "--count", "-n", help="Number of concept thumbnails to generate with FLUX (1-3)"),
    quantize: int = typer.Option(4, "--quantize", "-q", help="Quantization bits for FLUX (4 or 8)"),
):
    """🎨 Generate thumbnail concepts, render images locally via FLUX.1-schnell, and composite."""
    try:
        from adn.thumbnail import generate_all_thumbnails

        if not analysis_file.exists():
            console.print(f"[red]Error: File not found:[/red] {analysis_file}")
            raise typer.Exit(1)

        with open(analysis_file, "r", encoding="utf-8") as f:
            analysis = EpisodeAnalysis(**json.load(f))

        target_out_dir = output_dir or analysis_file.parent
        base_name = analysis_file.stem.replace("_analysis", "")
        generate_all_thumbnails(
            analysis=analysis,
            output_dir=target_out_dir,
            base_name=base_name,
            auto_render_images=True,
            use_local_flux=local,
            flux_quantize=quantize,
            flux_count=count,
        )
    except Exception as e:
        _handle_error(e)


@app.command(name="flux-render")
def flux_render_command(
    prompt: str = typer.Argument(..., help="Visual prompt description in English"),
    output_file: Path = typer.Option(Path("flux_output.png"), "--output", "-o", help="Target output image path"),
    headline: Optional[str] = typer.Option(None, "--headline", "-h", help="Optional headline text to composite"),
    subtext: Optional[str] = typer.Option(None, "--subtext", "-s", help="Optional subtext to composite"),
    quantize: int = typer.Option(4, "--quantize", "-q", help="Quantization (4 or 8)"),
):
    """⚡ Generate a single 16:9 image locally on Apple Silicon using FLUX.1-schnell."""
    try:
        from adn.thumbnail import create_thumbnail_composite, generate_local_flux_image

        raw_path = output_file.parent / f"{output_file.stem}_raw.png"
        success = generate_local_flux_image(
            prompt=prompt,
            output_path=raw_path,
            quantize=quantize,
            steps=4,
        )

        if success:
            if headline:
                create_thumbnail_composite(
                    background_image_path=raw_path,
                    output_thumbnail_path=output_file,
                    headline_text=headline,
                    subtext=subtext,
                )
            else:
                raw_path.rename(output_file)
            console.print(f"[bold green]✓ FLUX Render Complete:[/bold green] {output_file}")
        else:
            console.print("[red]✗ FLUX image generation failed.[/red]")
            raise typer.Exit(1)
    except Exception as e:
        _handle_error(e)


@app.command(name="composite-thumbnail")
def composite_thumbnail_command(
    image_file: Path = typer.Argument(..., help="Path to raw or generated background image (.png / .jpg)"),
    headline: str = typer.Option(..., "--headline", "-h", help="Bold uppercase headline (e.g. 'LA COMPASIÓN: ¿TIENE LÍMITES?')"),
    subtext: Optional[str] = typer.Option(None, "--subtext", "-s", help="Optional supporting subtitle"),
    output_path: Optional[Path] = typer.Option(None, "--output", "-o", help="Custom output image path"),
):
    """🖼️ Overlay ADN Divergente branding and high-impact typography onto any image."""
    try:
        from adn.thumbnail import create_thumbnail_composite

        if not image_file.exists():
            console.print(f"[red]Error: Image file not found:[/red] {image_file}")
            raise typer.Exit(1)

        target_out = output_path or (image_file.parent / f"{image_file.stem}_thumbnail.jpg")
        create_thumbnail_composite(
            background_image_path=image_file,
            output_thumbnail_path=target_out,
            headline_text=headline,
            subtext=subtext,
        )
    except Exception as e:
        _handle_error(e)


@app.command()
def auth():
    """🔑 Authenticate with YouTube Data API via browser OAuth."""
    try:
        from adn.uploader import get_youtube_service

        console.print("[cyan]Testing YouTube authentication...[/cyan]")
        youtube = get_youtube_service()
        # Verify by fetching authenticated user's channels
        response = youtube.channels().list(mine=True, part="snippet").execute()
        channels = response.get("items", [])
        if channels:
            ch_title = channels[0]["snippet"]["title"]
            console.print(f"[bold green]✓ Authenticated as YouTube Channel:[/bold green] [bold yellow]{ch_title}[/bold yellow]")
        else:
            console.print("[bold green]✓ YouTube authentication succeeded![/bold green]")
    except Exception as e:
        _handle_error(e)


@app.command()
def doctor():
    """🩺 Inspect system environment, FFmpeg status, AI keys, and YouTube OAuth."""
    table = Table(title="ADN Divergente Environment Health Check", border_style="cyan")
    table.add_column("Component", style="bold")
    table.add_column("Status", style="yellow")
    table.add_column("Details", style="dim")

    # Check FFmpeg
    ffmpeg = settings.ffmpeg_path
    if ffmpeg:
        table.add_row("FFmpeg", "[green]✓ Installed[/green]", ffmpeg)
    else:
        table.add_row("FFmpeg", "[red]✗ Missing[/red]", "Run: brew install ffmpeg-full")

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

    # Check YouTube OAuth Credentials
    secrets_file = Path("client_secrets.json")
    token_file = Path("token.json")
    if token_file.exists():
        table.add_row("YouTube OAuth", "[green]✓ Authenticated[/green]", "token.json active")
    elif secrets_file.exists():
        table.add_row("YouTube OAuth", "[yellow]Ready to Auth[/yellow]", "Run 'adn auth' to connect channel")
    else:
        table.add_row("YouTube OAuth", "[dim]○ Optional[/dim]", "Add client_secrets.json to enable auto-upload")

    # Check Local FLUX.1 Engine
    import shutil
    mflux_bin = Path(sys.executable).parent / "mflux-generate"
    if mflux_bin.exists() or shutil.which("mflux-generate"):
        table.add_row("Local Image AI", "[green]✓ FLUX.1-schnell[/green]", "MLX Metal GPU (4-bit/8-bit local)")
    else:
        table.add_row("Local Image AI", "[yellow]○ Not Installed[/yellow]", "Run 'uv sync'")

    console.print(table)


@app.command(name="studio")
def studio_command(
    path: Optional[Path] = typer.Argument(None, help="Optional specific directory to scan for episodes"),
    port: int = typer.Option(8000, "--port", "-p", help="Server port"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Server host"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not automatically open browser"),
):
    """🎨 Launch ADN Studio visual dashboard in your browser."""
    import uvicorn
    import webbrowser
    from adn.server import register_scan_path

    if path:
        register_scan_path(path.resolve())

    url = f"http://{host}:{port}"
    console.print(Panel(
        f"[bold yellow]ADN Divergente Visual Studio[/bold yellow]\n\n"
        f"🚀 Running at: [bold underline cyan]{url}[/bold underline cyan]\n"
        f"Press [bold red]Ctrl+C[/bold red] to stop the server.",
        border_style="yellow"
    ))

    if not no_browser:
        import threading
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    uvicorn.run("adn.server:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    app()
