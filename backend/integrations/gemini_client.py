from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import structlog

from backend.config import Settings

log = structlog.get_logger(__name__)


class GeminiUnavailable(RuntimeError):
    pass


class GeminiClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_key = settings.gemini_api_key
        self.vision_model = settings.gemini_vision_model
        self.research_model = settings.gemini_research_model
        self.extraction_model = settings.gemini_extraction_model
        self.poi_model = settings.gemini_poi_model
        self.anchor_image_model = settings.gemini_anchor_image_model
        self.fast_image_model = settings.gemini_fast_image_model
        self.skip_vision_detection = settings.skip_vision_detection

    def _client(self):
        if not self.api_key:
            raise GeminiUnavailable("GEMINI_API_KEY is not configured")
        from google import genai

        return genai.Client(api_key=self.api_key)

    async def generate_json(
        self,
        *,
        model: str,
        prompt: str,
        image_paths: list[str | Path] | None = None,
        response_schema: Any | None = None,
        use_google_search: bool = False,
    ) -> Any:
        client = self._client()
        from google.genai import types

        contents: list[Any] = []
        for image_path in image_paths or []:
            path = Path(image_path)
            contents.append(types.Part.from_bytes(data=path.read_bytes(), mime_type=_mime_type(path)))
        contents.append(prompt)

        tools = [types.Tool(google_search=types.GoogleSearch())] if use_google_search else None
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
            tools=tools,
        )
        started = time.perf_counter()
        response = await client.aio.models.generate_content(model=model, contents=contents, config=config)
        latency_ms = int((time.perf_counter() - started) * 1000)
        usage = getattr(response, "usage_metadata", None)
        log.info(
            "gemini_json_call",
            model=model,
            images_attached=len(image_paths or []),
            latency_ms=latency_ms,
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
        )
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            return parsed
        text = getattr(response, "text", "") or "{}"
        return json.loads(text)

    async def generate_text(
        self,
        *,
        model: str,
        prompt: str,
        use_google_search: bool = False,
    ) -> str:
        client = self._client()
        from google.genai import types

        tools = [types.Tool(google_search=types.GoogleSearch())] if use_google_search else None
        config = types.GenerateContentConfig(tools=tools)
        started = time.perf_counter()
        response = await client.aio.models.generate_content(model=model, contents=prompt, config=config)
        latency_ms = int((time.perf_counter() - started) * 1000)
        usage = getattr(response, "usage_metadata", None)
        log.info(
            "gemini_text_call",
            model=model,
            latency_ms=latency_ms,
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
        )
        return getattr(response, "text", "") or ""

    async def generate_image(
        self,
        *,
        model: str,
        prompt: str,
        reference_paths: list[str | Path],
    ) -> bytes:
        client = self._client()
        from google.genai import types

        contents: list[Any] = []
        for image_path in reference_paths:
            path = Path(image_path)
            contents.append(types.Part.from_bytes(data=path.read_bytes(), mime_type=_mime_type(path)))
        contents.append(prompt)
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio="16:9", image_size="2K"),
        )
        started = time.perf_counter()
        response = await client.aio.models.generate_content(model=model, contents=contents, config=config)
        latency_ms = int((time.perf_counter() - started) * 1000)
        usage = getattr(response, "usage_metadata", None)
        log.info(
            "gemini_image_call",
            model=model,
            images_attached=len(reference_paths),
            latency_ms=latency_ms,
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
        )
        for candidate in getattr(response, "candidates", []) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                inline_data = getattr(part, "inline_data", None)
                if inline_data and getattr(inline_data, "data", None):
                    return inline_data.data
        raise RuntimeError("Gemini image response did not include image bytes")


def _mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"
