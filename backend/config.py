from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    grabmaps_api_key: str | None = None
    grabmaps_base_url: str = "https://maps.grab.com"

    palimpsest_db_path: str = "./palimpsest.db"
    palimpsest_img_dir: Path = Path("./static/img")
    palimpsest_log_level: str = "INFO"

    karta_nearby_base_url: str = "https://kartaview.org"
    karta_api_base_url: str = "https://api.openstreetcam.org"

    gemini_vision_model: str = "gemini-3-pro-preview"
    gemini_research_model: str = "gemini-3-pro-preview"
    gemini_extraction_model: str = "gemini-3-flash-preview"
    gemini_poi_model: str = "gemini-3-flash-preview"
    gemini_anchor_image_model: str = "gemini-3-pro-image-preview"
    gemini_fast_image_model: str = "gemini-3.1-flash-image-preview"
    skip_vision_detection: bool = True
    prefer_cached_streetlevel: bool = False
    use_cached_streetlevel_fallback: bool = False
    cached_streetlevel_max_distance_m: int = 350
    fast_landmark_research: bool = False
    research_provider: Literal["openai", "gemini"] = "openai"
    area_research_enabled: bool = True
    area_research_timeout_s: float = 8.0
    area_research_max_chars: int = 18000
    openai_research_model: str = "gpt-5.4-mini"
    openai_research_timeout_s: float = 30.0
    openai_research_max_output_tokens: int = 1800
    openai_research_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh"] = "low"
    openai_research_external_web_access: bool = True
    openai_research_domains: str = (
        "wikipedia.org,roots.gov.sg,nlb.gov.sg,nas.gov.sg,ura.gov.sg"
    )
    fast_poi_enrichment: bool = True
    image_generation_concurrency: int = 2
    image_generation_start_interval_s: float = 2.0
    image_generation_max_retries: int = 4
    image_generation_retry_base_s: float = 6.0
    curated_cache_only: bool = True

    default_eras: list[int] = Field(default_factory=lambda: [1900, 1950, 1980, 2026])
    default_node_count: int = 4
    default_capture_radius_m: int = 100


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    db_path = Path(settings.palimpsest_db_path)
    if not db_path.is_absolute():
        settings.palimpsest_db_path = str((PROJECT_ROOT / db_path).resolve())
    if not settings.palimpsest_img_dir.is_absolute():
        settings.palimpsest_img_dir = (PROJECT_ROOT / settings.palimpsest_img_dir).resolve()
    settings.palimpsest_img_dir.mkdir(parents=True, exist_ok=True)
    return settings
