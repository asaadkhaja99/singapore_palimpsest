from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from backend.config import Settings

log = structlog.get_logger(__name__)


class OpenAIUnavailable(RuntimeError):
    pass


@dataclass
class OpenAIResearchResult:
    text: str
    sources: list[str]


class OpenAIClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_key = settings.openai_api_key
        self.base_url = settings.openai_base_url.rstrip("/")
        self.research_model = settings.openai_research_model

    async def research_text(
        self,
        *,
        prompt: str,
        model: str | None = None,
        allowed_domains: list[str] | None = None,
    ) -> OpenAIResearchResult:
        if not self.api_key:
            raise OpenAIUnavailable("OPENAI_API_KEY is not configured")

        payload: dict[str, Any] = {
            "model": model or self.research_model,
            "input": prompt,
            "tools": [
                {
                    "type": "web_search",
                    "search_context_size": "low",
                    "filters": {"allowed_domains": allowed_domains or self._research_domains()},
                    "external_web_access": self.settings.openai_research_external_web_access,
                    "user_location": {
                        "type": "approximate",
                        "country": "SG",
                        "city": "Singapore",
                        "region": "Singapore",
                    },
                }
            ],
            "tool_choice": "auto",
            "include": ["web_search_call.action.sources"],
            "max_output_tokens": self.settings.openai_research_max_output_tokens,
        }
        if self.settings.openai_research_reasoning_effort != "none":
            payload["reasoning"] = {"effort": self.settings.openai_research_reasoning_effort}

        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.settings.openai_research_timeout_s) as client:
            response = await client.post(
                f"{self.base_url}/responses",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            log.warning(
                "openai_research_failed",
                model=payload["model"],
                status_code=response.status_code,
                body=response.text[:1000],
                latency_ms=latency_ms,
            )
            response.raise_for_status()

        data = response.json()
        usage = data.get("usage") or {}
        text = _output_text(data)
        sources = _source_urls(data)
        log.info(
            "openai_research_call",
            model=payload["model"],
            latency_ms=latency_ms,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            source_count=len(sources),
        )
        return OpenAIResearchResult(text=text, sources=sources)

    def _research_domains(self) -> list[str]:
        return [
            domain.strip()
            for domain in self.settings.openai_research_domains.split(",")
            if domain.strip()
        ]


def _output_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    chunks: list[str] = []
    for item in data.get("output") or []:
        for content in item.get("content") or []:
            if isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()


def _source_urls(data: dict[str, Any]) -> list[str]:
    urls: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            url = value.get("url")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                urls.append(url)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data.get("output") or [])
    return list(dict.fromkeys(urls))
