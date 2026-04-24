from __future__ import annotations

from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont

from backend.integrations.gemini_client import GeminiClient, GeminiUnavailable


ANCHOR_MODEL = "gemini-3-pro-image-preview"
FAST_MODEL = "gemini-3.1-flash-image-preview"


async def generate_view_image(
    *,
    gemini: GeminiClient,
    prompt: str,
    reference_paths: list[str],
    out_path: str | Path,
    model: str,
) -> str:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if model == ANCHOR_MODEL:
        model = gemini.anchor_image_model
    elif model == FAST_MODEL:
        model = gemini.fast_image_model
    try:
        image_bytes = await gemini.generate_image(model=model, prompt=prompt, reference_paths=reference_paths)
        out_path.write_bytes(image_bytes)
    except GeminiUnavailable:
        _write_placeholder(out_path, reference_paths[0] if reference_paths else None, "Gemini key missing")
    except Exception as exc:
        _write_placeholder(out_path, reference_paths[0] if reference_paths else None, f"Generation failed: {exc}")
    return str(out_path)


def _write_placeholder(out_path: Path, reference_path: str | None, message: str) -> None:
    if reference_path:
        image = Image.open(reference_path).convert("RGB").resize((1280, 720), Image.Resampling.LANCZOS)
    else:
        image = Image.new("RGB", (1280, 720), "#222222")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 125))
    image = Image.alpha_composite(image.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    y = 300
    for line in wrap(message, 80):
        draw.text((40, y), line, fill=(255, 255, 255, 255), font=font)
        y += 22
    image.convert("RGB").save(out_path, quality=90)
