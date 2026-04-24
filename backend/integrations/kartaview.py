from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Any

import httpx
import structlog

from backend.config import Settings
from backend.integrations.street_level import StreetLevelPhoto, StreetLevelPhotoDetails
from backend.pipeline.geometry import angular_delta_deg, haversine_m

log = structlog.get_logger(__name__)


def _data_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("currentPageItems", "photos", "data", "items", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = _data_items(value)
                if nested:
                    return nested
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _payload_dict(payload: Any) -> dict[str, Any]:
    current = payload
    while isinstance(current, dict):
        for key in ("result", "data", "osv", "photo"):
            if isinstance(current.get(key), dict):
                current = current[key]
                break
        else:
            return current
    return {}


def _get(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item and item[key] is not None:
            return item[key]
    return None


def _photo_from_item(item: dict[str, Any], query_lat: float, query_lng: float) -> StreetLevelPhoto | None:
    photo_id = _get(item, "id", "photoId", "photo_id")
    lat = _get(item, "lat", "latitude")
    lng = _get(item, "lng", "lon", "longitude")
    if photo_id is None or lat is None or lng is None:
        return None
    projection = _get(item, "projection", "projectionType")
    fov = _get(item, "field_of_view", "fieldOfView", "fov")
    heading = _get(item, "heading", "compassAngle")
    return StreetLevelPhoto(
        photo_id=str(photo_id),
        sequence_id=str(_get(item, "sequence_id", "sequenceId")) if _get(item, "sequence_id", "sequenceId") else None,
        lat=float(lat),
        lng=float(lng),
        heading=float(heading) if heading is not None else None,
        shot_date=str(_get(item, "shot_date", "shotDate", "date_added", "dateAdded"))
        if _get(item, "shot_date", "shotDate", "date_added", "dateAdded")
        else None,
        projection=str(projection) if projection else None,
        field_of_view=float(fov) if fov is not None else None,
        distance_m=haversine_m(query_lat, query_lng, float(lat), float(lng)),
        image_url=_absolute_image_url(_get(item, "imageUrl", "fileurl", "fileUrl", "name")),
        image_proc_url=_processed_image_url(_get(item, "imageProcUrl", "fileurlProc", "fileUrlProc", "name")),
        thumbnail_url=_absolute_image_url(_get(item, "imageThUrl", "imageLthUrl", "lth_name", "th_name")),
    )


def _rank(photo: StreetLevelPhoto, heading_deg: float | None) -> tuple[float, float, float, float]:
    projection_penalty = 0 if (photo.projection or "").upper() == "SPHERE" else 1000
    fov_penalty = 0 if photo.field_of_view and photo.field_of_view >= 300 else 500
    heading_penalty = angular_delta_deg(photo.heading, heading_deg) if photo.heading is not None and heading_deg is not None else 90
    distance = photo.distance_m or 9999
    date_penalty = 0
    if photo.shot_date:
        # ISO-ish strings sort lexicographically, newer is better. This only breaks ties.
        date_penalty = -float("".join(ch for ch in photo.shot_date[:10] if ch.isdigit()) or 0) / 100000000
    return projection_penalty + fov_penalty, distance, heading_penalty, date_penalty


class KartaViewProvider:
    def __init__(self, settings: Settings):
        self.nearby_base_url = settings.karta_nearby_base_url.rstrip("/")
        self.api_base_url = settings.karta_api_base_url.rstrip("/")
        self.img_dir = settings.palimpsest_img_dir
        self._nearby_details: dict[str, StreetLevelPhotoDetails] = {}

    async def nearby_photos(
        self, lat: float, lng: float, radius_m: int, heading_deg: float | None = None
    ) -> list[StreetLevelPhoto]:
        requests = [_nearby_form(lat, lng, radius_m, heading_deg)]
        if heading_deg is not None:
            requests.append(_nearby_form(lat, lng, radius_m, None))
        seen: set[str] = set()
        photos: list[StreetLevelPhoto] = []
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            for data in requests:
                payload = await self._post_nearby(client, data)
                if payload is None:
                    continue
                for item in _data_items(payload):
                    photo = _photo_from_item(item, lat, lng)
                    if photo and photo.photo_id not in seen:
                        seen.add(photo.photo_id)
                        self._nearby_details[photo.photo_id] = StreetLevelPhotoDetails.model_validate(photo.model_dump())
                        photos.append(photo)
        return sorted(photos, key=lambda photo: _rank(photo, heading_deg))

    async def _post_nearby(self, client: httpx.AsyncClient, data: dict[str, str]) -> dict[str, Any] | None:
        bases = [self.nearby_base_url]
        if self.nearby_base_url != "https://api.openstreetcam.org":
            bases.append("https://api.openstreetcam.org")

        last_error = ""
        for base in bases:
            url = f"{base}/1.0/list/nearby-photos/"
            for attempt in range(3):
                try:
                    response = await client.post(url, data=data)
                    if response.status_code == 400:
                        last_error = response.text[:240]
                        await asyncio.sleep(0.7 * (attempt + 1))
                        continue
                    response.raise_for_status()
                    return response.json()
                except Exception as exc:
                    last_error = str(exc)
                    if attempt < 2:
                        await asyncio.sleep(0.7 * (attempt + 1))
            log.warning("kartaview_nearby_failed", url=url, data=data, error=last_error)
        return None

    async def photo_details(self, photo_id: str) -> StreetLevelPhotoDetails:
        fallback = self._nearby_details.get(photo_id)
        if fallback and (fallback.image_proc_url or fallback.image_url):
            return fallback

        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            payload: dict[str, Any] | None = None
            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    response = await client.get(f"{self.api_base_url}/2.0/photo/{photo_id}")
                    response.raise_for_status()
                    payload = response.json()
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < 2:
                        await asyncio.sleep(0.75 * (attempt + 1))
            if payload is None:
                if last_error:
                    raise last_error
                raise RuntimeError(f"KartaView photo details unavailable for {photo_id}")
        data = _payload_dict(payload)
        lat = float(_get(data, "lat", "latitude") or 0)
        lng = float(_get(data, "lng", "lon", "longitude") or 0)
        heading = _get(data, "heading", "compassAngle")
        fov = _get(data, "fieldOfView", "field_of_view", "fov")
        return StreetLevelPhotoDetails(
            photo_id=str(_get(data, "id", "photoId", "photo_id") or photo_id),
            sequence_id=str(_get(data, "sequenceId", "sequence_id")) if _get(data, "sequenceId", "sequence_id") else None,
            lat=lat,
            lng=lng,
            heading=float(heading) if heading is not None else None,
            shot_date=str(_get(data, "shotDate", "shot_date", "dateAdded", "date_added"))
            if _get(data, "shotDate", "shot_date", "dateAdded", "date_added")
            else None,
            projection=str(_get(data, "projection", "projectionType")) if _get(data, "projection", "projectionType") else None,
            field_of_view=float(fov) if fov is not None else None,
            image_url=_absolute_image_url(_get(data, "imageUrl", "fileurl", "fileUrl", "name")),
            image_proc_url=_processed_image_url(_get(data, "imageProcUrl", "fileurlProc", "fileUrlProc", "name")),
            thumbnail_url=_absolute_image_url(_get(data, "imageThUrl", "imageLthUrl", "th_name", "lth_name")),
            width=int(_get(data, "width")) if _get(data, "width") is not None else None,
            height=int(_get(data, "height")) if _get(data, "height") is not None else None,
        )

    async def download_source_image(self, details: StreetLevelPhotoDetails) -> Path:
        url = details.image_proc_url or details.image_url
        if not url:
            raise RuntimeError(f"KartaView photo {details.photo_id} has no downloadable image URL")
        out_dir = self.img_dir / "kartaview" / "source"
        out_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".jpg"
        out_path = out_dir / f"{details.photo_id}{suffix}"
        if out_path.exists() and out_path.stat().st_size > 0:
            return out_path
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            response = await client.get(str(url))
            response.raise_for_status()
            out_path.write_bytes(response.content)
        return out_path


def _nearby_form(lat: float, lng: float, radius_m: int, heading_deg: float | None) -> dict[str, str]:
    data = {
        "lat": str(lat),
        "lng": str(lng),
        "radius": str(radius_m),
        "page": "1",
        "ipp": "50",
    }
    if heading_deg is not None:
        data["heading"] = str(heading_deg)
    return data


def _absolute_image_url(value: Any) -> str | None:
    if not value:
        return None
    url = str(value).replace("{{sizeprefix}}", "wrapped_proc")
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("storage") and "/" in url:
        storage, rest = url.split("/", 1)
        return f"https://{storage}.openstreetcam.org/{rest}"
    return url


def _processed_image_url(value: Any) -> str | None:
    url = _absolute_image_url(value)
    if not url:
        return None
    if "cdn.kartaview.org/" in url:
        return url
    url = url.replace("/proc/", "/wrapped_proc/")
    encoded = base64.b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")
    return f"https://cdn.kartaview.org/pr:sharp/{encoded}"
