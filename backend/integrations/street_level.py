from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel


class StreetLevelPhoto(BaseModel):
    photo_id: str
    sequence_id: str | None = None
    lat: float
    lng: float
    heading: float | None = None
    shot_date: str | None = None
    projection: str | None = None
    field_of_view: float | None = None
    distance_m: float | None = None
    image_url: str | None = None
    image_proc_url: str | None = None
    thumbnail_url: str | None = None


class StreetLevelPhotoDetails(StreetLevelPhoto):
    width: int | None = None
    height: int | None = None


class StreetLevelProvider(Protocol):
    async def nearby_photos(
        self, lat: float, lng: float, radius_m: int, heading_deg: float | None = None
    ) -> list[StreetLevelPhoto]: ...

    async def photo_details(self, photo_id: str) -> StreetLevelPhotoDetails: ...

    async def download_source_image(self, details: StreetLevelPhotoDetails) -> Path: ...
