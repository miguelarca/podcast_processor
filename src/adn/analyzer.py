"""AI Content Analyzer for ADN Divergente podcast transcripts."""

import json
from pathlib import Path
from typing import Optional
from rich.console import Console

from adn.config import settings
from adn.models import EpisodeAnalysis, Transcript

console = Console()

SYSTEM_PROMPT = """\
Eres el Director Editorial y Estratega de Contenido Digital del podcast "ADN Divergente".
En ADN Divergente, dos hermanos conversan de forma franca, reflexiva, sin filtros ni rodeos sobre temas sociales, culturales, económicos, filosóficos y de actualidad.

Tu misión es analizar la transcripción completa de un episodio (con marcas de tiempo) y generar una estrategia completa de publicación y corte de video.

Debes generar:
1. **Resumen del Episodio y Temas Clave**: Síntesis clara y profunda de las tesis debatidas.
2. **10 Opciones de Títulos para YouTube**: Títulos magnéticos, con alto CTR, en español, que despierten curiosidad sin caer en clickbait engañoso. Clasifícalos por estilo (curiosity, debate, question, story, contrarian).
3. **Capítulos de YouTube (Timestamps)**: Marcadores de tiempo claros y atractivos con formato exacto (ej. "00:00 - Introducción", "04:15 - El dilema de...").
4. **Descripción de YouTube Completa**: Lista para copiar y pegar, incluyendo sinopsis, capítulos, llamados a la acción y hashtags.
5. **Candidatos a Clips / Mini-Episodios (Estilo Lex Clips)**: 3 a 6 segmentos autónomos de 3 a 10 minutos de duración. Cada clip debe contener una discusión completa, un debate con inicio, desarrollo y conclusión contundente, con sus marcas de tiempo exactas (en segundos) y título llamativo.
6. **Candidatos a Shorts / Reels / TikTok**: 4 a 8 momentos electrizantes de 30 a 75 segundos. Frases polémicas, remates reflexivos o momentos de humor/tensión con la cita gancho exacta.
7. **Contenido para Redes Sociales**: Hilo para X/Twitter (3-5 tweets), post reflexivo para LinkedIn, y copy con emojis para Instagram.

Responde ÚNICAMENTE con el objeto JSON que cumpla con el esquema requerido.
"""


def _prepare_transcript_text_with_timestamps(transcript: Transcript) -> str:
    """Format transcript with timestamps every ~30 seconds for LLM context."""
    lines = []
    for seg in transcript.segments:
        mins = int(seg.start // 60)
        secs = int(seg.start % 60)
        lines.append(f"[{mins:02d}:{secs:02d} | {seg.start:.1f}s - {seg.end:.1f}s] {seg.text}")
    return "\n".join(lines)


def analyze_with_gemini(transcript: Transcript) -> EpisodeAnalysis:
    """Run analysis using Google Gemini API with structured JSON output."""
    from google import genai
    from google.genai import types

    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set in .env")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    transcript_text = _prepare_transcript_text_with_timestamps(transcript)

    user_prompt = f"""Analiza la siguiente transcripción del episodio de ADN Divergente (Duración total: {transcript.duration / 60:.1f} minutos):

--- INICIO TRANSCRIPCIÓN ---
{transcript_text}
--- FIN TRANSCRIPCIÓN ---
"""

    console.print(f"[cyan]Analyzing transcript with Gemini 2.5 Flash...[/cyan]")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=f"{SYSTEM_PROMPT}\n\n{user_prompt}")]
            )
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=EpisodeAnalysis,
            temperature=0.4,
        ),
    )

    return EpisodeAnalysis.model_validate_json(response.text)


def analyze_with_openai(transcript: Transcript) -> EpisodeAnalysis:
    """Run analysis using OpenAI GPT-4o with structured JSON output."""
    from openai import OpenAI

    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not set in .env")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    transcript_text = _prepare_transcript_text_with_timestamps(transcript)

    user_prompt = f"""Analiza la siguiente transcripción del episodio de ADN Divergente:

--- INICIO TRANSCRIPCIÓN ---
{transcript_text}
--- FIN TRANSCRIPCIÓN ---
"""

    console.print(f"[cyan]Analyzing transcript with OpenAI GPT-4o...[/cyan]")
    response = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format=EpisodeAnalysis,
        temperature=0.4,
    )

    return response.choices[0].message.parsed


def run_analysis(
    transcript: Transcript,
    output_dir: Path,
    base_name: str,
    provider: Optional[str] = None
) -> EpisodeAnalysis:
    """Orchestrate LLM analysis and save metadata files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{base_name}_analysis.json"
    desc_path = output_dir / f"{base_name}_youtube_description.txt"

    if json_path.exists():
        console.print(f"[green]Found cached analysis:[/green] {json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return EpisodeAnalysis(**data)

    chosen_provider = provider or settings.DEFAULT_LLM_PROVIDER
    if chosen_provider == "openai":
        analysis = analyze_with_openai(transcript)
    else:
        analysis = analyze_with_gemini(transcript)

    # Save JSON analysis
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(analysis.model_dump_json(indent=2))

    # Save ready-to-paste YouTube description
    with open(desc_path, "w", encoding="utf-8") as f:
        f.write(f"=== DESCRIPCIÓN SUGERIDA PARA YOUTUBE ===\n\n")
        f.write(analysis.youtube_description)
        f.write("\n\n=== OPCIONES DE TÍTULOS ===\n")
        for opt in analysis.title_options:
            f.write(f"- [{opt.style.upper()}] {opt.title}\n  Razón: {opt.rationale}\n")

    console.print(f"[green]Saved analysis and show notes to:[/green] {output_dir}")
    return analysis
