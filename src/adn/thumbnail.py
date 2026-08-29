"""Thumbnail ideation, prompt engineering, and visual compositing for ADN Divergente."""

import json
import subprocess
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw, ImageFont
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from adn.config import settings
from adn.models import EpisodeAnalysis

console = Console()


class ThumbnailConcept(BaseModel):
    id: str = Field(..., description="Concept identifier (e.g. 'thumb_01').")
    headline_text: str = Field(..., description="High-impact Spanish text to put on the thumbnail (e.g. 'LA COMPASIÓN: ¿TIENE LÍMITES?').")
    subtext: Optional[str] = Field(None, description="Short supporting subtitle in Spanish (e.g. 'Debo seguir ayudando al otro').")
    visual_metaphor: str = Field(..., description="Explanation of the conceptual metaphor and visual contrast.")
    gemini_prompt: str = Field(..., description="Detailed English prompt for Gemini / Imagen 3 / Midjourney to generate the background scene.")


class ThumbnailPack(BaseModel):
    concepts: List[ThumbnailConcept]


THUMBNAIL_SYSTEM_PROMPT = """\
Eres el Director de Arte y Diseñador Visual Principal del podcast "ADN Divergente".
Observa la línea gráfica característica de las miniaturas de ADN Divergente:
- Formato 16:9 panorámico de alto impacto para YouTube.
- Ilustraciones conceptuales y cinematográficas con metáforas visuales potentes (ej. contrastes sociales, psicología humana, árboles genealógicos, debates morales, cerebro bajo estrés, manos ayudando vs salvavidas).
- Iluminación dramática, colores cálidos pero intensos, gran nivel de detalle visual que despierta curiosidad inmediata.
- Titulares grandes, en mayúsculas, directos y provocadores (ej. "LA COMPASIÓN: ¿TIENE LÍMITES?", "¿LA POBREZA ES FELICIDAD?", "LA FAMILIA: TU PIEDRA FUNDAMENTAL").

Tu tarea es generar 3 conceptos visuales distintos para la miniatura del episodio, con sus titulares en español y los prompts detallados en inglés listos para generar la imagen en Gemini/Imagen/Midjourney.
"""


def generate_thumbnail_concepts(analysis: EpisodeAnalysis) -> List[ThumbnailConcept]:
    """Generate 3 high-CTR thumbnail concepts and Gemini image prompts."""
    from google import genai
    from google.genai import types

    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set in .env")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    prompt = f"""Genera 3 conceptos de miniaturas estilo ADN Divergente para el siguiente episodio:

Resumen del episodio: {analysis.episode_summary}
Temas clave: {', '.join(analysis.core_themes)}
Opciones de títulos: {', '.join([t.title for t in analysis.title_options[:5]])}
"""

    console.print(f"[cyan]Generating thumbnail concepts and Gemini image prompts...[/cyan]")
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=f"{THUMBNAIL_SYSTEM_PROMPT}\n\n{prompt}",
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ThumbnailPack,
            temperature=0.7,
        ),
    )

    pack = ThumbnailPack.model_validate_json(response.text)
    return pack.concepts


def generate_single_image(prompt: str, output_path: Path) -> bool:
    """Attempt to generate an actual image file via Gemini or OpenAI APIs."""
    from google import genai
    from google.genai import types

    # 1. Try Google Gemini Flash Image API
    if settings.GEMINI_API_KEY:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        for model in ["gemini-2.5-flash-image", "gemini-3.1-flash-image"]:
            try:
                res = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
                )
                for part in res.candidates[0].content.parts:
                    if part.inline_data:
                        with open(output_path, "wb") as img_out:
                            img_out.write(part.inline_data.data)
                        return True
            except Exception:
                continue

    # 2. Fallback to OpenAI DALL-E 3 if configured
    if settings.OPENAI_API_KEY:
        try:
            from openai import OpenAI
            import requests

            oa_client = OpenAI(api_key=settings.OPENAI_API_KEY)
            resp = oa_client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1792x1024",
                quality="standard",
                n=1,
            )
            img_url = resp.data[0].url
            img_bytes = requests.get(img_url).content
            with open(output_path, "wb") as img_out:
                img_out.write(img_bytes)
            return True
        except Exception:
            pass

    return False


def save_thumbnail_pack(concepts: List[ThumbnailConcept], output_dir: Path, base_name: str) -> Path:
    """Save thumbnail prompts and concepts to file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    prompts_file = output_dir / f"{base_name}_thumbnail_prompts.txt"
    json_file = output_dir / f"{base_name}_thumbnail_concepts.json"

    with open(json_file, "w", encoding="utf-8") as f:
        f.write(json.dumps([c.model_dump() for c in concepts], indent=2, ensure_ascii=False))

    with open(prompts_file, "w", encoding="utf-8") as f:
        f.write("=== PROMPTS DE MINIATURAS PARA GEMINI / MIDJOURNEY ===\n\n")
        for i, c in enumerate(concepts, 1):
            f.write(f"🎨 CONCEPTO {i}: {c.headline_text}\n")
            if c.subtext:
                f.write(f"   Subtítulo: {c.subtext}\n")
            f.write(f"   Metáfora: {c.visual_metaphor}\n\n")
            f.write(f"   PROMPT LISTO PARA PEGAR EN GEMINI:\n")
            f.write(f"   \"{c.gemini_prompt}\"\n\n")
            f.write("-" * 60 + "\n\n")

    return prompts_file


def generate_all_thumbnails(
    analysis: EpisodeAnalysis,
    output_dir: Path,
    base_name: str,
    auto_render_images: bool = True
) -> Path:
    """Master orchestrator for thumbnail concept ideation, generation, and compositing."""
    thumbs_dir = output_dir / "thumbnails"
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    concepts = generate_thumbnail_concepts(analysis=analysis)
    prompts_file = save_thumbnail_pack(concepts=concepts, output_dir=thumbs_dir, base_name=base_name)
    display_thumbnail_concepts(concepts)

    if auto_render_images:
        console.print("\n[cyan]Attempting direct AI image generation for thumbnail concepts...[/cyan]")
        successful_renders = 0

        for i, c in enumerate(concepts, 1):
            raw_img_path = thumbs_dir / f"thumb_{i:02d}_background.png"
            final_thumb_path = thumbs_dir / f"thumb_{i:02d}_final.jpg"

            console.print(f"  [{i}/{len(concepts)}] Generating image for: '{c.headline_text}'...")
            if generate_single_image(prompt=c.gemini_prompt, output_path=raw_img_path):
                create_thumbnail_composite(
                    background_image_path=raw_img_path,
                    output_thumbnail_path=final_thumb_path,
                    headline_text=c.headline_text,
                    subtext=c.subtext,
                )
                successful_renders += 1
            else:
                console.print(f"  [yellow]○ Direct API generation unavailable for concept {i}.[/yellow]")

        if successful_renders > 0:
            console.print(f"[bold green]✨ Successfully generated {successful_renders} thumbnail images in:[/bold green] {thumbs_dir}")
        else:
            console.print(
                Panel(
                    "[bold yellow]ℹ️  Direct Image Generation API Quota Note[/bold yellow]\n\n"
                    "Google AI Studio's Free Tier includes text & transcript analysis at $0 cost, "
                    "while direct API image generation requires Pay-As-You-Go billing enabled.\n\n"
                    f"👉 [bold green]Easy Free Option:[/bold green] Copy the prompts saved in:\n"
                    f"[bold underline]{prompts_file}[/bold underline]\n"
                    "Paste them into [bold cyan]gemini.google.com[/bold cyan] or [bold cyan]Midjourney[/bold cyan] for free, "
                    "then run:\n"
                    "[bold]uv run adn composite-thumbnail /path/to/downloaded.png --headline \"TITULAR\"[/bold]",
                    border_style="yellow"
                )
            )

    return prompts_file


def display_thumbnail_concepts(concepts: List[ThumbnailConcept]):
    """Render thumbnail options in a rich terminal table."""
    table = Table(title="🎨 Conceptos de Miniaturas para YouTube (Estilo ADN Divergente)", border_style="magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Titular en Miniatura", style="bold yellow", width=30)
    table.add_column("Subtítulo", style="white", width=25)
    table.add_column("Metáfora Visual", style="dim")

    for i, c in enumerate(concepts, 1):
        table.add_row(str(i), c.headline_text, c.subtext or "", c.visual_metaphor)

    console.print(table)


def create_thumbnail_composite(
    background_image_path: Path,
    output_thumbnail_path: Path,
    headline_text: str,
    subtext: Optional[str] = None,
    badge_text: str = "EPISODIO DISPONIBLE",
) -> Path:
    """Composite ADN Divergente branding and stylized text onto a 1280x720 thumbnail."""
    output_thumbnail_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Open and resize background to standard 1280x720 (16:9)
    img = Image.open(background_image_path).convert("RGBA")
    img = img.resize((1280, 720), Image.Resampling.LANCZOS)

    # 2. Add subtle dark gradient overlay at the top/bottom for high text readability
    overlay = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)

    # Top gradient for logo
    draw_overlay.rectangle([(0, 0), (1280, 100)], fill=(0, 0, 0, 80))
    # Bottom gradient for text
    draw_overlay.rectangle([(0, 520), (1280, 720)], fill=(0, 0, 0, 130))
    img = Image.alpha_composite(img, overlay)

    draw = ImageDraw.Draw(img)

    # Try to load high-impact system fonts
    font_paths = [
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/System/Library/Fonts/Supplemental/Arial Black.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    font_main = None
    for fp in font_paths:
        if Path(fp).exists():
            try:
                font_main = ImageFont.truetype(fp, size=56)
                font_sub = ImageFont.truetype(fp, size=32)
                font_badge = ImageFont.truetype(fp, size=24)
                break
            except Exception:
                continue

    if not font_main:
        font_main = font_sub = font_badge = ImageFont.load_default()

    # 3. Draw Top-Left Brand Logo "ADN DIVERGENTE"
    draw.text((40, 30), "ADN DIVERGENTE", font=font_badge, fill=(255, 204, 0, 255), stroke_width=3, stroke_fill=(0, 0, 0, 255))

    # 4. Draw Main Headline (Centered / Bottom)
    headline_clean = headline_text.upper()
    # Draw with thick black stroke for maximum contrast
    draw.text(
        (640, 570),
        headline_clean,
        font=font_main,
        fill=(255, 255, 255, 255),
        stroke_width=6,
        stroke_fill=(0, 0, 0, 255),
        anchor="ms"
    )

    # 5. Draw Subtext if present
    if subtext:
        draw.text(
            (640, 630),
            subtext,
            font=font_sub,
            fill=(255, 220, 50, 255),
            stroke_width=4,
            stroke_fill=(0, 0, 0, 255),
            anchor="ms"
        )

    # 6. Save as PNG
    final_img = img.convert("RGB")
    final_img.save(output_thumbnail_path, format="JPEG", quality=95)
    console.print(f"[bold green]✓ Created Thumbnail Composite:[/bold green] {output_thumbnail_path.name}")
    return output_thumbnail_path
