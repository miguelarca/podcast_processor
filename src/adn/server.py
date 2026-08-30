"""ADN Studio: Local FastAPI backend for visual post-production suite."""

import asyncio
import json
import os
import mimetypes
from pathlib import Path
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, Request, Response, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from adn.config import settings
from adn.models import EpisodeAnalysis, Transcript, YouTubeChapter
from adn.thumbnail import (
    create_thumbnail_composite,
    generate_thumbnail_concepts,
    save_thumbnail_pack,
    generate_local_flux_image,
)
from adn.uploader import (
    get_youtube_service,
    upload_video,
    upload_full_episode,
    upload_all_shorts_batch,
    upload_all_clips_batch,
)

app = FastAPI(title="ADN Studio", description="ADN Divergente Local Visual Post-Production Suite")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active scan directories
SCAN_DIRS: List[Path] = [
    Path.cwd() / "output",
    Path("/Volumes/T9/videos"),
]

# Track active background jobs
JOB_STATUS: Dict[str, Dict[str, Any]] = {}


def register_scan_path(path: Path):
    """Add a directory to the scan paths if not already present."""
    if path.exists() and path not in SCAN_DIRS:
        SCAN_DIRS.insert(0, path)


def find_all_episodes() -> List[Dict[str, Any]]:
    """Scan known locations for processed episode directories."""
    episodes = []
    seen_dirs = set()

    for base_dir in SCAN_DIRS:
        if not base_dir.exists():
            continue

        # Look for analysis files
        analysis_files = list(base_dir.glob("**/*_analysis.json"))
        for af in analysis_files:
            ep_dir = af.parent
            if ep_dir in seen_dirs:
                continue
            seen_dirs.add(ep_dir)

            try:
                with open(af, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Check video file
                video_file = None
                for ext in [".mp4", ".mov", ".mkv", ".webm"]:
                    candidate = ep_dir / f"{ep_dir.name}{ext}"
                    if candidate.exists():
                        video_file = candidate
                        break
                    # Also check parent directory for source video
                    candidate_parent = ep_dir.parent / f"{ep_dir.name}{ext}"
                    if candidate_parent.exists():
                        video_file = candidate_parent
                        break

                episodes.append({
                    "id": ep_dir.name,
                    "name": ep_dir.name.replace("_", " ").title(),
                    "directory": str(ep_dir),
                    "analysis_path": str(af),
                    "video_path": str(video_file) if video_file else None,
                    "summary": data.get("episode_summary", "")[:200] + "...",
                    "core_themes": data.get("core_themes", []),
                    "clips_count": len(data.get("clips", [])),
                    "shorts_count": len(data.get("shorts", [])),
                })
            except Exception:
                continue

    return episodes


# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------

@app.get("/api/episodes")
def list_episodes():
    """List all available processed episodes."""
    return find_all_episodes()


@app.get("/api/episodes/{episode_id}")
def get_episode_details(episode_id: str, path: Optional[str] = None):
    """Get complete metadata, analysis, clips, shorts, and thumbnails for an episode."""
    ep_dir = Path(path) if path else None
    if not ep_dir or not ep_dir.exists():
        # Search scan directories
        for sdir in SCAN_DIRS:
            candidate = sdir / episode_id
            if candidate.exists():
                ep_dir = candidate
                break

    if not ep_dir or not ep_dir.exists():
        raise HTTPException(status_code=404, detail="Episode directory not found")

    analysis_file = ep_dir / f"{episode_id}_analysis.json"
    if not analysis_file.exists():
        analysis_files = list(ep_dir.glob("*_analysis.json"))
        if analysis_files:
            analysis_file = analysis_files[0]
        else:
            raise HTTPException(status_code=404, detail="Analysis JSON not found in episode folder")

    with open(analysis_file, "r", encoding="utf-8") as f:
        analysis_data = json.load(f)

    # Locate source video
    video_path = None
    for ext in [".mp4", ".mov", ".mkv", ".webm"]:
        cand = ep_dir / f"{episode_id}{ext}"
        if cand.exists():
            video_path = cand
            break
        cand_parent = ep_dir.parent / f"{episode_id}{ext}"
        if cand_parent.exists():
            video_path = cand_parent
            break

    # Locate 16:9 clips
    clips_dir = ep_dir / "clips"
    clips_list = []
    if clips_dir.exists():
        for clip_file in sorted(clips_dir.glob("clip_*.mp4")):
            clips_list.append({
                "filename": clip_file.name,
                "path": str(clip_file),
                "url": f"/api/media/stream?path={clip_file}",
            })

    # Locate 9:16 vertical shorts
    shorts_dir = ep_dir / "shorts"
    shorts_list = []
    if shorts_dir.exists():
        for short_file in sorted(shorts_dir.glob("short_*.mp4")):
            shorts_list.append({
                "filename": short_file.name,
                "path": str(short_file),
                "url": f"/api/media/stream?path={short_file}",
            })

    # Locate thumbnails
    thumbs_dir = ep_dir / "thumbnails"
    thumbs_list = []
    if thumbs_dir.exists():
        raw_files = sorted(thumbs_dir.glob("*.jpg")) + sorted(thumbs_dir.glob("*.png"))
        for thumb_file in raw_files:
            if thumb_file.name.startswith(".") or thumb_file.stat().st_size < 1000:
                continue
            thumbs_list.append({
                "filename": thumb_file.name,
                "path": str(thumb_file),
                "url": f"/api/media/stream?path={thumb_file}",
            })

    # Read transcript if available
    transcript_file = ep_dir / f"{episode_id}_transcript.json"
    transcript_data = None
    if transcript_file.exists():
        try:
            with open(transcript_file, "r", encoding="utf-8") as tf:
                transcript_data = json.load(tf)
        except Exception:
            pass

    return {
        "id": episode_id,
        "directory": str(ep_dir),
        "video_path": str(video_path) if video_path else None,
        "video_url": f"/api/media/stream?path={video_path}" if video_path else None,
        "analysis": analysis_data,
        "transcript": transcript_data,
        "clips": clips_list,
        "shorts": shorts_list,
        "thumbnails": thumbs_list,
    }


class SaveEpisodePayload(BaseModel):
    title: Optional[str] = None
    youtube_description: Optional[str] = None
    chapters: Optional[List[Dict[str, Any]]] = None


@app.post("/api/episodes/{episode_id}/save")
def save_episode_metadata(episode_id: str, payload: SaveEpisodePayload, path: str):
    """Save edited title, description, and chapters to analysis.json."""
    ep_dir = Path(path)
    analysis_file = ep_dir / f"{episode_id}_analysis.json"
    if not analysis_file.exists():
        analysis_files = list(ep_dir.glob("*_analysis.json"))
        if analysis_files:
            analysis_file = analysis_files[0]
        else:
            raise HTTPException(status_code=404, detail="Analysis file not found")

    with open(analysis_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    if payload.title:
        # Prepend or set as title_options[0]
        if "title_options" in data and data["title_options"]:
            data["title_options"][0]["title"] = payload.title
        else:
            data["title_options"] = [{"style": "custom", "title": payload.title, "rationale": "Custom user title"}]

    if payload.youtube_description:
        data["youtube_description"] = payload.youtube_description
        # Also write to standalone description txt
        desc_file = ep_dir / f"{episode_id}_youtube_description.txt"
        with open(desc_file, "w", encoding="utf-8") as df:
            df.write(payload.youtube_description)

    if payload.chapters:
        data["chapters"] = payload.chapters

    with open(analysis_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return {"status": "saved", "message": "Episode metadata saved successfully"}


# -----------------------------------------------------------------------------
# Media Streaming (HTTP 206 Partial Content for smooth scrubbing)
# -----------------------------------------------------------------------------

@app.get("/api/media/stream")
def stream_media(path: str, request: Request):
    """Stream audio, video, or image files with Range support."""
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    mime_type, _ = mimetypes.guess_type(str(file_path))
    mime_type = mime_type or "application/octet-stream"

    # For images, return regular FileResponse
    if mime_type.startswith("image/"):
        return FileResponse(file_path, media_type=mime_type)

    file_size = file_path.stat().st_size
    range_header = request.headers.get("Range")

    if not range_header:
        # Initial chunk
        return FileResponse(file_path, media_type=mime_type)

    # Parse Range: bytes=start-end
    try:
        range_str = range_header.replace("bytes=", "")
        parts = range_str.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else min(start + 1024 * 1024 * 5, file_size - 1)  # 5MB chunks
    except Exception:
        start = 0
        end = file_size - 1

    length = end - start + 1

    def iter_file():
        with open(file_path, "rb") as f:
            f.seek(start)
            bytes_read = 0
            while bytes_read < length:
                chunk_size = min(64 * 1024, length - bytes_read)
                data = f.read(chunk_size)
                if not data:
                    break
                bytes_read += len(data)
                yield data

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Content-Type": mime_type,
    }
    return StreamingResponse(iter_file(), status_code=206, headers=headers)


# -----------------------------------------------------------------------------
# Thumbnail Studio Endpoints
# -----------------------------------------------------------------------------

class CompositeThumbnailPayload(BaseModel):
    background_image_path: str
    headline_text: str
    subtext: Optional[str] = None
    badge_text: str = "EPISODIO COMPLETO"
    output_path: Optional[str] = None


@app.post("/api/thumbnails/composite")
def composite_thumbnail(payload: CompositeThumbnailPayload):
    """Composite headline, subtext, and badges onto an image."""
    bg_path = Path(payload.background_image_path)
    if not bg_path.exists():
        raise HTTPException(status_code=404, detail="Background image not found")

    out_path = Path(payload.output_path) if payload.output_path else (bg_path.parent / f"{bg_path.stem}_composite.jpg")
    result = create_thumbnail_composite(
        background_image_path=bg_path,
        output_thumbnail_path=out_path,
        headline_text=payload.headline_text,
        subtext=payload.subtext,
        badge_text=payload.badge_text,
    )
    return {
        "status": "success",
        "path": str(result),
        "url": f"/api/media/stream?path={result}&t={os.path.getmtime(result)}",
    }


class ClipThumbnailPromptPayload(BaseModel):
    title: str
    hook: Optional[str] = ""
    summary: Optional[str] = ""


@app.post("/api/thumbnails/clip-concept")
def generate_clip_thumbnail_concept(payload: ClipThumbnailPromptPayload):
    """Generate a high-CTR visual metaphor and prompt for a specific 16:9 clip."""
    from google import genai
    from google.genai import types
    from adn.thumbnail import ThumbnailConcept

    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY not configured")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    sys_prompt = (
        "Eres el Director de Arte de ADN Divergente. Para el siguiente extracto o clip, crea un prompt en inglés "
        "para FLUX/Midjourney (16:9, arte conceptual cinematográfico, iluminación dramática con contrastes, metáfora visual potente) "
        "y sugiere un titular corto de 2 a 5 palabras en mayúsculas para la miniatura."
    )
    user_prompt = f"Título del Clip: {payload.title}\nGancho/Hook: {payload.hook}\nResumen: {payload.summary}"

    res = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=f"{sys_prompt}\n\n{user_prompt}",
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ThumbnailConcept,
            temperature=0.7,
        )
    )
    concept = ThumbnailConcept.model_validate_json(res.text)
    return concept.model_dump()


class FluxGeneratePayload(BaseModel):
    prompt: str
    output_path: str
    quantize: int = 4
    headline_text: Optional[str] = None
    subtext: Optional[str] = None


@app.post("/api/thumbnails/flux-generate")
async def generate_flux_thumbnail(payload: FluxGeneratePayload, background_tasks: BackgroundTasks):
    """Generate image locally using FLUX.1-schnell on Apple Silicon Metal GPU."""
    out_path = Path(payload.output_path)
    job_id = f"flux_{int(asyncio.get_event_loop().time())}"
    JOB_STATUS[job_id] = {"status": "running", "message": "Rendering with FLUX.1-schnell on Metal GPU..."}

    def run_flux():
        try:
            raw_path = out_path.parent / f"{out_path.stem}_raw.png"
            success = generate_local_flux_image(
                prompt=payload.prompt,
                output_path=raw_path,
                quantize=payload.quantize,
                steps=4,
            )
            if success:
                if payload.headline_text:
                    create_thumbnail_composite(
                        background_image_path=raw_path,
                        output_thumbnail_path=out_path,
                        headline_text=payload.headline_text,
                        subtext=payload.subtext,
                    )
                else:
                    raw_path.rename(out_path)
                JOB_STATUS[job_id] = {
                    "status": "completed",
                    "path": str(out_path),
                    "url": f"/api/media/stream?path={out_path}",
                }
            else:
                JOB_STATUS[job_id] = {"status": "failed", "message": "FLUX generation failed"}
        except Exception as e:
            JOB_STATUS[job_id] = {"status": "failed", "message": str(e)}

    background_tasks.add_task(run_flux)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    """Poll job status."""
    if job_id not in JOB_STATUS:
        raise HTTPException(status_code=404, detail="Job not found")
    return JOB_STATUS[job_id]


# -----------------------------------------------------------------------------
# YouTube Publishing & Authentication
# -----------------------------------------------------------------------------

@app.get("/api/youtube/status")
def get_youtube_auth_status():
    """Check YouTube OAuth status and return channel info."""
    token_file = Path("token.json")
    if not token_file.exists():
        return {"authenticated": False, "channel": None}

    try:
        youtube = get_youtube_service()
        res = youtube.channels().list(mine=True, part="snippet").execute()
        items = res.get("items", [])
        if items:
            snippet = items[0]["snippet"]
            return {
                "authenticated": True,
                "channel": {
                    "title": snippet["title"],
                    "customUrl": snippet.get("customUrl", ""),
                    "thumbnail": snippet["thumbnails"]["default"]["url"],
                }
            }
        return {"authenticated": True, "channel": {"title": "Connected"}}
    except Exception as e:
        return {"authenticated": False, "error": str(e)}


class YouTubeUploadPayload(BaseModel):
    video_path: str
    analysis_path: str
    title: Optional[str] = None
    description: Optional[str] = None
    privacy: str = "unlisted"
    thumbnail_path: Optional[str] = None


@app.post("/api/youtube/upload-episode")
async def publish_full_episode(payload: YouTubeUploadPayload, background_tasks: BackgroundTasks):
    """Publish main full episode to YouTube."""
    job_id = f"upload_{int(asyncio.get_event_loop().time())}"
    JOB_STATUS[job_id] = {"status": "uploading", "progress": 0, "message": "Uploading video chunks to YouTube..."}

    def run_upload():
        try:
            vid_path = Path(payload.video_path)
            an_path = Path(payload.analysis_path)
            th_path = Path(payload.thumbnail_path) if payload.thumbnail_path else None

            video_id = upload_full_episode(
                video_path=vid_path,
                analysis_path=an_path,
                custom_title=payload.title,
                privacy_status=payload.privacy,
                thumbnail_path=th_path,
            )
            JOB_STATUS[job_id] = {
                "status": "completed",
                "video_id": video_id,
                "url": f"https://youtu.be/{video_id}",
            }
        except Exception as e:
            JOB_STATUS[job_id] = {"status": "failed", "message": str(e)}

    background_tasks.add_task(run_upload)
    return {"job_id": job_id, "status": "queued"}


# -----------------------------------------------------------------------------
# In-Studio Pipeline Runner for New Episodes
# -----------------------------------------------------------------------------

class ProcessPipelinePayload(BaseModel):
    video_path: str
    whisper_backend: Optional[str] = "faster-whisper"
    skip_cuts: bool = False
    skip_shorts: bool = False


@app.post("/api/pipeline/process")
async def start_pipeline_process(payload: ProcessPipelinePayload, background_tasks: BackgroundTasks):
    """Run full post-production pipeline on a new video recording directly from ADN Studio."""
    video_file = Path(payload.video_path)
    if not video_file.exists():
        raise HTTPException(status_code=400, detail=f"Video file not found at: {payload.video_path}")

    job_id = f"proc_{int(asyncio.get_event_loop().time())}"
    JOB_STATUS[job_id] = {
        "status": "running",
        "stage": "starting",
        "progress": 5,
        "message": "Inicializando pipeline...",
        "logs": [f"Iniciando procesamiento para: {video_file.name}"],
    }

    def run_pipeline():
        try:
            from adn.transcriber import run_transcription
            from adn.analyzer import run_analysis
            from adn.cutter import cut_all_clips
            from adn.shorts import generate_all_shorts
            from adn.thumbnail import generate_all_thumbnails

            base_name = video_file.stem
            target_out_dir = video_file.parent / base_name
            target_out_dir.mkdir(parents=True, exist_ok=True)
            register_scan_path(target_out_dir.parent)

            # 1. Transcribe
            JOB_STATUS[job_id]["stage"] = "transcribing"
            JOB_STATUS[job_id]["progress"] = 20
            JOB_STATUS[job_id]["message"] = "Transcribiendo audio en español con Whisper..."
            JOB_STATUS[job_id]["logs"].append("Extrayendo audio y transcribiendo...")
            transcript = run_transcription(input_file=video_file, output_dir=target_out_dir, backend=payload.whisper_backend)
            JOB_STATUS[job_id]["logs"].append(f"Transcripción finalizada ({transcript.duration / 60:.1f} min).")

            # 2. Analyze with Gemini
            JOB_STATUS[job_id]["stage"] = "analyzing"
            JOB_STATUS[job_id]["progress"] = 45
            JOB_STATUS[job_id]["message"] = "Analizando con Gemini 3.6 Flash..."
            JOB_STATUS[job_id]["logs"].append("Generando 10 títulos, capítulos, clips y shorts...")
            analysis = run_analysis(transcript=transcript, output_dir=target_out_dir, base_name=base_name)
            JOB_STATUS[job_id]["logs"].append(f"Análisis editorial completado.")

            # 3. Cut 16:9 Clips
            if not payload.skip_cuts:
                JOB_STATUS[job_id]["stage"] = "cutting_clips"
                JOB_STATUS[job_id]["progress"] = 65
                JOB_STATUS[job_id]["message"] = "Cortando clips 16:9..."
                JOB_STATUS[job_id]["logs"].append(f"Cortando {len(analysis.clips)} mini-episodios 16:9...")
                cut_all_clips(input_video=video_file, clips=analysis.clips, output_dir=target_out_dir)

            # 4. Generate 9:16 Shorts
            if not payload.skip_shorts:
                JOB_STATUS[job_id]["stage"] = "generating_shorts"
                JOB_STATUS[job_id]["progress"] = 85
                JOB_STATUS[job_id]["message"] = "Renderizando shorts 9:16 con subtítulos animados..."
                JOB_STATUS[job_id]["logs"].append(f"Generando {len(analysis.shorts)} shorts verticales...")
                generate_all_shorts(input_video=video_file, transcript=transcript, shorts=analysis.shorts, output_dir=target_out_dir)

            # 5. Thumbnails
            JOB_STATUS[job_id]["stage"] = "thumbnails"
            JOB_STATUS[job_id]["progress"] = 95
            JOB_STATUS[job_id]["message"] = "Generando conceptos de miniaturas..."
            generate_all_thumbnails(analysis=analysis, output_dir=target_out_dir, base_name=base_name, auto_render_images=False)

            JOB_STATUS[job_id]["status"] = "completed"
            JOB_STATUS[job_id]["progress"] = 100
            JOB_STATUS[job_id]["message"] = "¡Episodio procesado exitosamente!"
            JOB_STATUS[job_id]["episode_id"] = base_name
            JOB_STATUS[job_id]["directory"] = str(target_out_dir)
            JOB_STATUS[job_id]["logs"].append("Procesamiento finalizado con éxito.")
        except Exception as e:
            JOB_STATUS[job_id]["status"] = "failed"
            JOB_STATUS[job_id]["message"] = str(e)
            JOB_STATUS[job_id]["logs"].append(f"Error fatal: {e}")

    background_tasks.add_task(run_pipeline)
    return {"job_id": job_id, "status": "queued"}


# -----------------------------------------------------------------------------
# Serve Static Frontend
# -----------------------------------------------------------------------------

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def get_index_page():
    """Serve the main studio single page app."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>ADN Studio UI Initializing...</h1>")
