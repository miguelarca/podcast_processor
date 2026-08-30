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


def generate_local_flux_image(
    prompt: str,
    output_path: Path,
    quantize: int = 4,
    steps: int = 4,
    width: int = 1280,
    height: int = 720,
) -> bool:
    """Generate high quality 16:9 image locally on Apple Silicon Metal GPU via FLUX.1-schnell."""
    import sys
    import shutil

    output_path.parent.mkdir(parents=True, exist_ok=True)
    mflux_bin = Path(sys.executable).parent / "mflux-generate"
    if not mflux_bin.exists():
        mflux_str = shutil.which("mflux-generate")
        if not mflux_str:
            return False
        mflux_bin = Path(mflux_str)

    cmd = [
        str(mflux_bin),
        "--model", "schnell",
        "--quantize", str(quantize),
        "--prompt", prompt,
        "--steps", str(steps),
        "--width", str(width),
        "--height", str(height),
        "--output", str(output_path),
    ]

    import os
    env = os.environ.copy()
    if settings.HF_TOKEN:
        env["HF_TOKEN"] = settings.HF_TOKEN
        env["HUGGING_FACE_HUB_TOKEN"] = settings.HF_TOKEN

    console.print(f"  [cyan]⚡ Generating with local FLUX.1-schnell on Apple Silicon ({steps} steps, {quantize}-bit)...[/cyan]")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    if res.returncode == 0 and output_path.exists():
        return True
    else:
        err_msg = res.stderr.strip() or res.stdout.strip()
        if "401" in err_msg or "Unauthorized" in err_msg:
            console.print(
                Panel(
                    "[bold yellow]🔑 Hugging Face Authentication Required for FLUX.1[/bold yellow]\n\n"
                    "Black Forest Labs requires accepting their terms to download FLUX.1-schnell weights:\n"
                    "1. Go to: [bold cyan]https://huggingface.co/black-forest-labs/FLUX.1-schnell[/bold cyan] and click 'Agree'.\n"
                    "2. Get your free token at: [bold cyan]https://huggingface.co/settings/tokens[/bold cyan]\n"
                    "3. Add to your [bold].env[/bold] file:\n"
                    "   [bold green]HF_TOKEN=hf_...[/bold green]\n",
                    border_style="yellow"
                )
            )
        elif err_msg:
            console.print(f"  [yellow]Local FLUX notice:[/yellow] {err_msg[:200]}")
        return False


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
    auto_render_images: bool = True,
    use_local_flux: bool = True,
    flux_quantize: int = 4,
    flux_count: int = 1,
) -> Path:
    """Master orchestrator for thumbnail concept ideation, generation, and compositing."""
    thumbs_dir = output_dir / "thumbnails"
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    concepts = generate_thumbnail_concepts(analysis=analysis)
    prompts_file = save_thumbnail_pack(concepts=concepts, output_dir=thumbs_dir, base_name=base_name)
    display_thumbnail_concepts(concepts)

    if auto_render_images:
        console.print("\n[bold cyan]Generating thumbnail images and composites...[/bold cyan]")
        successful_renders = 0

        # Limit count if desired (default renders concept 1 or up to flux_count)
        concepts_to_render = concepts[:flux_count]

        for i, c in enumerate(concepts_to_render, 1):
            raw_img_path = thumbs_dir / f"thumb_{i:02d}_flux_raw.png"
            final_thumb_path = thumbs_dir / f"thumb_{i:02d}_final.jpg"

            console.print(f"\n[bold magenta][{i}/{len(concepts_to_render)}] Rendering: '{c.headline_text}'[/bold magenta]")
            generated = False

            # 1. First priority: Local Apple Silicon FLUX.1-schnell
            if use_local_flux:
                generated = generate_local_flux_image(
                    prompt=c.gemini_prompt,
                    output_path=raw_img_path,
                    quantize=flux_quantize,
                    steps=4,
                )

            # 2. Second priority: Cloud API (Gemini / OpenAI)
            if not generated:
                generated = generate_single_image(prompt=c.gemini_prompt, output_path=raw_img_path)

            # 3. Composite text & branding onto generated image
            if generated:
                create_thumbnail_composite(
                    background_image_path=raw_img_path,
                    output_thumbnail_path=final_thumb_path,
                    headline_text=c.headline_text,
                    subtext=c.subtext,
                )
                successful_renders += 1
            else:
                console.print(f"  [yellow]○ Image generation skipped for concept {i}.[/yellow]")

        if successful_renders > 0:
            console.print(f"\n[bold green]✨ Successfully generated {successful_renders} thumbnail images in:[/bold green] {thumbs_dir}")
        else:
            console.print(
                Panel(
                    "[bold yellow]ℹ️  Manual Prompt Option[/bold yellow]\n\n"
                    f"You can copy any of the prompts saved in:\n"
                    f"[bold underline]{prompts_file}[/bold underline]\n"
                    "Paste into [bold cyan]gemini.google.com[/bold cyan], download the image, and run:\n"
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


def _wrap_text_to_width(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> List[str]:
    """Wrap text into multiple lines so that no line exceeds max_width."""
    words = text.split()
    if not words:
        return []

    lines = []
    current_line = []

    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font, stroke_width=6)
        line_w = bbox[2] - bbox[0]
        if line_w <= max_width or not current_line:
            current_line.append(word)
        else:
            lines.append(" ".join(current_line))
            current_line = [word]

    if current_line:
        lines.append(" ".join(current_line))

    return lines


def create_thumbnail_composite(
    background_image_path: Path,
    output_thumbnail_path: Path,
    headline_text: str,
    subtext: Optional[str] = None,
    badge_text: str = "EPISODIO COMPLETO",
    position: str = "bottom",
) -> Path:
    """Composite ADN Divergente branding and stylized auto-fitting text onto a 1280x720 thumbnail."""
    output_thumbnail_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Open and resize background to standard 1280x720 (16:9)
    img = Image.open(background_image_path).convert("RGBA")
    img = img.resize((1280, 720), Image.Resampling.LANCZOS)

    # 2. Font candidates lookup
    font_paths = [
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/System/Library/Fonts/Supplemental/Arial Black.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    font_file = None
    for fp in font_paths:
        if Path(fp).exists():
            font_file = fp
            break

    # 3. Dynamic Font Auto-Sizer & Wrapper
    # Target maximum text block width is 1140px (70px padding each side)
    max_text_width = 1140
    headline_clean = headline_text.strip().upper()

    # Try font sizes from 64 down to 36
    headline_lines = []
    font_headline = None
    font_sub = None
    font_size_used = 60

    temp_draw = ImageDraw.Draw(img)

    for f_size in range(64, 34, -4):
        if font_file:
            try:
                f_h = ImageFont.truetype(font_file, size=f_size)
            except Exception:
                f_h = ImageFont.load_default()
        else:
            f_h = ImageFont.load_default()

        lines = _wrap_text_to_width(headline_clean, f_h, max_text_width, temp_draw)
        # We prefer at most 2 lines for the headline (3 lines if unavoidable)
        if len(lines) <= 2:
            font_headline = f_h
            headline_lines = lines
            font_size_used = f_size
            break
        elif f_size <= 36:
            font_headline = f_h
            headline_lines = lines
            font_size_used = f_size

    if not font_headline:
        font_headline = ImageFont.load_default()
        headline_lines = [headline_clean]

    # Subtitle font (approx 55% of headline size)
    sub_font_size = max(24, int(font_size_used * 0.55))
    if font_file:
        try:
            font_sub = ImageFont.truetype(font_file, size=sub_font_size)
            font_badge = ImageFont.truetype(font_file, size=24)
            font_small_badge = ImageFont.truetype(font_file, size=18)
        except Exception:
            font_sub = font_badge = font_small_badge = ImageFont.load_default()
    else:
        font_sub = font_badge = font_small_badge = ImageFont.load_default()

    # Wrap subtext if present
    subtext_lines = []
    if subtext:
        subtext_lines = _wrap_text_to_width(subtext.strip(), font_sub, max_text_width - 100, temp_draw)

    # 4. Calculate total text block height and positions
    line_spacing = 8
    line_heights = []
    for line in headline_lines:
        bbox = temp_draw.textbbox((0, 0), line, font=font_headline, stroke_width=6)
        line_heights.append(bbox[3] - bbox[1])

    sub_line_heights = []
    for line in subtext_lines:
        bbox = temp_draw.textbbox((0, 0), line, font=font_sub, stroke_width=4)
        sub_line_heights.append(bbox[3] - bbox[1])

    total_headline_h = sum(line_heights) + (len(line_heights) - 1) * line_spacing
    total_sub_h = (sum(sub_line_heights) + (len(sub_line_heights) - 1) * 6 + 14) if subtext_lines else 0
    total_content_h = total_headline_h + total_sub_h

    # Base Y positioning (leave 40px safe space from bottom for YouTube progress bar)
    start_y = 660 - total_content_h

    # 5. Build Smooth Dark Backdrop Gradient behind text
    overlay = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)

    # Top brand bar scrim
    draw_overlay.rectangle([(0, 0), (1280, 90)], fill=(0, 0, 0, 110))

    # Bottom gradient overlay (covers from start_y - 40 to 720)
    grad_top = max(0, int(start_y - 45))
    draw_overlay.rectangle([(0, grad_top), (1280, 720)], fill=(0, 0, 0, 160))
    img = Image.alpha_composite(img, overlay)

    draw = ImageDraw.Draw(img)

    # 6. Draw Top-Left Brand Logo "ADN DIVERGENTE" with yellow highlight
    draw.rectangle([(30, 22), (235, 62)], fill=(0, 0, 0, 200), outline=(255, 204, 0, 255), width=2)
    draw.text((42, 28), "ADN DIVERGENTE", font=font_badge, fill=(255, 204, 0, 255))

    # 7. Draw Bottom-Left "EPISODIO COMPLETO" Badge
    draw.rectangle([(35, 665), (210, 695)], fill=(220, 38, 38, 230))
    draw.text((45, 670), badge_text.upper(), font=font_small_badge, fill=(255, 255, 255, 255))

    # 8. Draw Headline Lines (Centered, with thick outline)
    current_y = start_y
    for i, line in enumerate(headline_lines):
        # Alternate line colors: Line 1 white, Line 2 bright yellow for visual punch
        text_color = (255, 255, 255, 255) if (i % 2 == 0) else (255, 220, 40, 255)
        draw.text(
            (640, current_y),
            line,
            font=font_headline,
            fill=text_color,
            stroke_width=7,
            stroke_fill=(0, 0, 0, 255),
            anchor="mt"
        )
        current_y += line_heights[i] + line_spacing

    # 9. Draw Subtext Lines
    if subtext_lines:
        current_y += 10
        for line in subtext_lines:
            draw.text(
                (640, current_y),
                line,
                font=font_sub,
                fill=(255, 235, 100, 255),
                stroke_width=4,
                stroke_fill=(0, 0, 0, 255),
                anchor="mt"
            )
            current_y += (sub_line_heights[0] if sub_line_heights else 28) + 6

    # 10. Save as high quality JPEG
    final_img = img.convert("RGB")
    final_img.save(output_thumbnail_path, format="JPEG", quality=95)
    console.print(f"[bold green]✓ Created Auto-Fitted Thumbnail:[/bold green] {output_thumbnail_path}")
    return output_thumbnail_path
