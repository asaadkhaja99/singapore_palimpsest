from __future__ import annotations

import asyncio
import random
from io import BytesIO
from pathlib import Path
from textwrap import wrap

import structlog
from PIL import Image, ImageDraw, ImageFont, ImageStat

from backend.integrations.gemini_client import GeminiClient, GeminiUnavailable


ANCHOR_MODEL = "gemini-3-pro-image-preview"
FAST_MODEL = "gemini-3.1-flash-image-preview"
MIN_MEAN_SATURATION = 34.0

log = structlog.get_logger(__name__)


class ImageGenerationFailed(RuntimeError):
    pass


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
        image_bytes = await _generate_image_with_retries(
            gemini=gemini,
            model=model,
            prompt=prompt,
            reference_paths=reference_paths,
        )
        if _mean_saturation(image_bytes) < MIN_MEAN_SATURATION:
            log.warning("image_generation_low_saturation_retry", model=model, out_path=str(out_path))
            image_bytes = await _generate_image_with_retries(
                gemini=gemini,
                model=model,
                prompt=enforce_colour_prompt(prompt),
                reference_paths=reference_paths,
            )
        out_path.write_bytes(image_bytes)
    except GeminiUnavailable:
        raise
    except Exception as exc:
        raise ImageGenerationFailed(f"Image generation failed for {out_path}: {exc}") from exc
    return str(out_path)


async def _generate_image_with_retries(
    *,
    gemini: GeminiClient,
    model: str,
    prompt: str,
    reference_paths: list[str],
) -> bytes:
    settings = gemini.settings
    max_retries = max(0, settings.image_generation_max_retries)
    base_delay = max(0.25, settings.image_generation_retry_base_s)
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await gemini.generate_image(model=model, prompt=prompt, reference_paths=reference_paths)
        except GeminiUnavailable:
            raise
        except Exception as exc:
            last_exc = exc
            if attempt >= max_retries or not _is_retryable_generation_error(exc):
                raise
            delay = _retry_delay_s(exc, attempt, base_delay)
            log.warning(
                "gemini_image_retry",
                model=model,
                attempt=attempt + 1,
                max_retries=max_retries,
                delay_s=round(delay, 2),
                error=str(exc),
            )
            await asyncio.sleep(delay)
    raise RuntimeError(last_exc or "image generation retry failed")


def enforce_colour_prompt(prompt: str) -> str:
    return (
        f"{prompt}\n\n"
        "COLOUR REQUIREMENT: Regenerate as a vivid but realistic "
        "full-colour scene with natural coloured building materials, signs, sky, road surface, plants, "
        "and clothing. Do not use black-and-white, sepia, grayscale, or faded archival styling."
    )


def _mean_saturation(image_bytes: bytes) -> float:
    with Image.open(BytesIO(image_bytes)) as image:
        hsv = image.convert("RGB").resize((256, 144), Image.Resampling.BILINEAR).convert("HSV")
        return float(ImageStat.Stat(hsv.getchannel("S")).mean[0])


def _is_retryable_generation_error(exc: Exception) -> bool:
    status = _status_code(exc)
    if status in {429, 500, 502, 503, 504}:
        return True
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "429",
            "too many requests",
            "resource_exhausted",
            "quota",
            "rate limit",
            "temporarily unavailable",
            "server error",
        )
    )


def _retry_delay_s(exc: Exception, attempt: int, base_delay: float) -> float:
    retry_after = _retry_after_s(exc)
    if retry_after is not None:
        return retry_after + random.uniform(0.0, 1.5)
    return min(90.0, base_delay * (2**attempt)) + random.uniform(0.0, 2.5)


def _status_code(exc: Exception) -> int | None:
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def _retry_after_s(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    value = headers.get("retry-after") if hasattr(headers, "get") else None
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


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
