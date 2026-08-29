"""YouTube automated uploader using the official YouTube Data API v3."""

import json
import os
import time
from pathlib import Path
from typing import List, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TimeRemainingColumn, TransferSpeedColumn

from adn.models import EpisodeAnalysis, Transcript

console = Console()

# OAuth Scopes needed for upload, thumbnail, and caption management
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube",
]


def get_youtube_service(
    client_secrets_path: Optional[Path] = None,
    token_path: Optional[Path] = None
):
    """Authenticate and build the YouTube Data API v3 service."""
    secrets_file = client_secrets_path or Path("client_secrets.json")
    token_file = token_path or Path("token.json")

    creds = None
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            console.print("[cyan]Refreshing YouTube OAuth credentials...[/cyan]")
            creds.refresh(Request())
        else:
            if not secrets_file.exists():
                raise FileNotFoundError(
                    f"YouTube OAuth credentials file '{secrets_file}' not found.\n\n"
                    "How to get it:\n"
                    "1. Go to Google Cloud Console (https://console.cloud.google.com/apis/credentials)\n"
                    "2. Enable 'YouTube Data API v3'\n"
                    "3. Create OAuth 2.0 Client ID (Desktop Application)\n"
                    "4. Download JSON and save as 'client_secrets.json' in this folder."
                )
            console.print("[cyan]Initiating YouTube OAuth authentication (opening browser)...[/cyan]")
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save credentials for future headless runs
        with open(token_file, "w", encoding="utf-8") as token_f:
            token_f.write(creds.to_json())
        console.print(f"[green]Saved authentication token to {token_file}[/green]")

    return build("youtube", "v3", credentials=creds)


def upload_video(
    youtube,
    video_path: Path,
    title: str,
    description: str,
    tags: Optional[List[str]] = None,
    category_id: str = "24",  # 24 = Entertainment, 22 = People & Blogs, 27 = Education
    privacy_status: str = "unlisted",  # "private", "unlisted", "public"
    thumbnail_path: Optional[Path] = None,
    srt_path: Optional[Path] = None,
) -> str:
    """Upload a video file with resumable chunking and progress tracking."""
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    # YouTube max title length is 100 characters
    clean_title = title[:100]

    body = {
        "snippet": {
            "title": clean_title,
            "description": description,
            "tags": tags or ["ADN Divergente", "Podcast", "Sociedad", "Cultura", "Debate"],
            "categoryId": category_id,
            "defaultLanguage": "es",
            "defaultAudioLanguage": "es",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/*",
        resumable=True,
        chunksize=1024 * 1024 * 5,  # 5MB chunks
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    console.print(f"\n[bold cyan]Uploading to YouTube:[/bold cyan] {clean_title}")
    console.print(f"[dim]File: {video_path.name} | Privacy: {privacy_status}[/dim]")

    file_size = video_path.stat().st_size
    response = None

    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
    ) as progress:
        upload_task = progress.add_task("Uploading video", total=file_size)

        while response is None:
            status, response = request.next_chunk()
            if status:
                progress.update(upload_task, completed=status.resumable_progress)

    video_id = response.get("id")
    video_url = f"https://youtu.be/{video_id}"
    console.print(f"[bold green]✓ Video uploaded successfully![/bold green] [bold underline]{video_url}[/bold underline]")

    # Upload Custom Thumbnail if provided
    if thumbnail_path and thumbnail_path.exists():
        try:
            console.print(f"[cyan]Uploading custom thumbnail...[/cyan]")
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/png")
            ).execute()
            console.print(f"[green]✓ Custom thumbnail uploaded.[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠️  Failed to set custom thumbnail:[/yellow] {e}")

    # Upload Closed Captions (SRT) if provided
    if srt_path and srt_path.exists():
        try:
            console.print(f"[cyan]Uploading native Spanish subtitles track...[/cyan]")
            caption_body = {
                "snippet": {
                    "videoId": video_id,
                    "language": "es",
                    "name": "Español (ADN)",
                    "isDraft": False,
                }
            }
            youtube.captions().insert(
                part="snippet",
                body=caption_body,
                media_body=MediaFileUpload(str(srt_path), mimetype="*/*")
            ).execute()
            console.print(f"[green]✓ Subtitles (.srt) track uploaded.[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠️  Could not attach subtitles track:[/yellow] {e}")

    return video_id


def upload_full_episode(
    video_path: Path,
    analysis_path: Path,
    transcript_path: Optional[Path] = None,
    custom_title: Optional[str] = None,
    privacy_status: str = "unlisted",
    thumbnail_path: Optional[Path] = None,
) -> str:
    """Orchestrate uploading a full episode using existing analysis metadata."""
    with open(analysis_path, "r", encoding="utf-8") as f:
        analysis = EpisodeAnalysis(**json.load(f))

    # Determine title: custom, or first high-CTR title option
    title = custom_title or (analysis.title_options[0].title if analysis.title_options else video_path.stem)
    description = analysis.youtube_description
    tags = list(set(["ADN Divergente", "Podcast"] + analysis.core_themes[:8]))

    # Locate SRT if not explicitly provided
    srt_file = transcript_path
    if not srt_file:
        candidate_srt = analysis_path.parent / f"{analysis_path.stem.replace('_analysis', '')}_transcript.srt"
        if candidate_srt.exists():
            srt_file = candidate_srt

    youtube = get_youtube_service()
    return upload_video(
        youtube=youtube,
        video_path=video_path,
        title=title,
        description=description,
        tags=tags,
        privacy_status=privacy_status,
        thumbnail_path=thumbnail_path,
        srt_path=srt_file,
    )


def upload_all_shorts_batch(
    shorts_dir: Path,
    analysis_path: Path,
    privacy_status: str = "unlisted"
) -> List[str]:
    """Upload all generated vertical shorts (.mp4) in a directory."""
    with open(analysis_path, "r", encoding="utf-8") as f:
        analysis = EpisodeAnalysis(**json.load(f))

    shorts_lookup = {sanitize_title(s.title): s for s in analysis.shorts}
    video_files = sorted(list(shorts_dir.glob("short_*.mp4")))

    if not video_files:
        raise FileNotFoundError(f"No shorts found in {shorts_dir}")

    youtube = get_youtube_service()
    uploaded_ids = []

    console.print(f"[bold magenta]Starting batch upload of {len(video_files)} YouTube Shorts...[/bold magenta]")

    for idx, short_file in enumerate(video_files, start=1):
        # Match short metadata from analysis
        title = f"Short {idx:02d} | ADN Divergente #shorts"
        quote = ""
        for clean_name, s in shorts_lookup.items():
            if clean_name in short_file.name:
                title = f"{s.title} #shorts"
                quote = s.hook_quote
                break

        description = (
            f"{quote}\n\n"
            f"🎙️ Extracto del podcast ADN Divergente.\n"
            f"Suscríbete para más episodios completos y reflexiones candidas.\n\n"
            f"#shorts #ADNDivergente #Podcast #Reflexion #Debate"
        )
        tags = ["ADN Divergente", "Shorts", "Podcast", "Viral", "YouTube Shorts"]

        console.print(f"\n[{idx}/{len(video_files)}] Uploading Short: {short_file.name}")
        vid_id = upload_video(
            youtube=youtube,
            video_path=short_file,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status,
        )
        uploaded_ids.append(vid_id)

    return uploaded_ids


def sanitize_title(title: str) -> str:
    import re
    s = re.sub(r"[^\w\s-]", "", title).strip().lower()
    return re.sub(r"[-\s]+", "_", s)[:40]
