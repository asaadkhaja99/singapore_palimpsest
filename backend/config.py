from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str | None = None
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
    prefer_cached_streetlevel: bool = True
    use_cached_streetlevel_fallback: bool = True
    cached_streetlevel_max_distance_m: int = 350
    fast_landmark_research: bool = False
    area_research_enabled: bool = True
    area_research_timeout_s: float = 8.0
    area_research_max_chars: int = 18000
    fast_poi_enrichment: bool = True
    image_generation_concurrency: int = 4
    image_generation_start_interval_s: float = 0.5

    default_eras: list[int] = Field(default_factory=lambda: [1900, 1950, 1980, 2026])
    default_node_count: int = 4
    default_capture_radius_m: int = 100


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.palimpsest_img_dir.mkdir(parents=True, exist_ok=True)
    return settings
