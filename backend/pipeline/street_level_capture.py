from __future__ import annotations

from pathlib import Path

from backend.config import Settings
from backend.integrations.street_level import StreetLevelProvider
from backend.pipeline.geometry import haversine_m
from backend.pipeline.projection import create_direction_crops
from backend.pipeline.types import StreetLevelCapture


class StreetLevelUnavailable(RuntimeError):
    pass


async def capture_street_level(
    *,
    settings: Settings,
    provider: StreetLevelProvider,
    lat: float,
    lng: float,
    heading_deg: float,
    node_key: str,
    radius_steps_m: tuple[int, ...] = (100, 200, 300),
) -> StreetLevelCapture:
    if settings.prefer_cached_streetlevel:
        cached = _cached_capture(settings, lat, lng, heading_deg)
        if cached:
            return cached

    try:
        return await _capture_live(
            settings=settings,
            provider=provider,
            lat=lat,
            lng=lng,
            heading_deg=heading_deg,
            node_key=node_key,
            radius_steps_m=radius_steps_m,
        )
    except Exception as exc:
        if settings.use_cached_streetlevel_fallback:
            cached = _cached_capture(settings, lat, lng, heading_deg)
            if cached:
                return cached
        if isinstance(exc, StreetLevelUnavailable):
            raise
        raise StreetLevelUnavailable(str(exc)) from exc


async def _capture_live(
    *,
    settings: Settings,
    provider: StreetLevelProvider,
    lat: float,
    lng: float,
    heading_deg: float,
    node_key: str,
    radius_steps_m: tuple[int, ...],
) -> StreetLevelCapture:
    photos = []
    for radius_m in radius_steps_m:
        photos = await provider.nearby_photos(lat, lng, radius_m=radius_m, heading_deg=heading_deg)
        if photos:
            break
    if not photos:
        raise StreetLevelUnavailable(f"No KartaView/OpenStreetCam photo found within {radius_steps_m[-1]}m")

    spherical = [
        photo
        for photo in photos
        if (photo.projection or "").upper() == "SPHERE" or (photo.field_of_view is not None and photo.field_of_view >= 300)
    ]
    if not spherical:
        raise StreetLevelUnavailable("KartaView imagery was found nearby, but no spherical 360-degree photo was available")
    selected = spherical[0]
    details = await provider.photo_details(selected.photo_id)
    source_path = await provider.download_source_image(details)
    crop_dir = settings.palimpsest_img_dir / "kartaview" / "crops" / node_key
    crop_paths = create_direction_crops(
        source_path=source_path,
        output_dir=crop_dir,
        source_heading_deg=details.heading or selected.heading,
    )
    return StreetLevelCapture(
        requested_lat=lat,
        requested_lng=lng,
        requested_heading_deg=heading_deg,
        photo_id=details.photo_id,
        sequence_id=details.sequence_id or selected.sequence_id,
        source_lat=details.lat or selected.lat,
        source_lng=details.lng or selected.lng,
        source_heading_deg=details.heading or selected.heading,
        source_capture_date=details.shot_date or selected.shot_date,
        source_image_path=str(Path(source_path)),
        reference_crop_paths=crop_paths,
        projection=details.projection or selected.projection,
    )


def _cached_capture(settings: Settings, lat: float, lng: float, heading_deg: float) -> StreetLevelCapture | None:
    crop_root = settings.palimpsest_img_dir / "kartaview" / "crops"
    if not crop_root.exists():
        return None

    candidates: list[tuple[float, Path, float, float, dict[str, str]]] = []
    for child in crop_root.iterdir():
        if not child.is_dir():
            continue
        coords = _coords_from_cache_key(child.name)
        if coords is None:
            continue
        crop_paths = _crop_paths(child)
        if crop_paths is None:
            continue
        cached_lat, cached_lng = coords
        distance = haversine_m(lat, lng, cached_lat, cached_lng)
        if distance <= settings.cached_streetlevel_max_distance_m:
            candidates.append((distance, child, cached_lat, cached_lng, crop_paths))

    if not candidates:
        return None
    _, crop_dir, source_lat, source_lng, crop_paths = sorted(candidates, key=lambda item: item[0])[0]
    return StreetLevelCapture(
        provider="cached-kartaview",
        requested_lat=lat,
        requested_lng=lng,
        requested_heading_deg=heading_deg,
        photo_id=f"cached_{crop_dir.name}",
        sequence_id=None,
        source_lat=source_lat,
        source_lng=source_lng,
        source_heading_deg=heading_deg,
        source_capture_date="cached",
        source_image_path=crop_paths["N"],
        reference_crop_paths=crop_paths,
        projection="SPHERE",
    )


def _coords_from_cache_key(name: str) -> tuple[float, float] | None:
    parts = name.split("_")
    if len(parts) < 2:
        return None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None


def _crop_paths(crop_dir: Path) -> dict[str, str] | None:
    paths = {}
    for direction in ("N", "E", "S", "W"):
        path = crop_dir / f"{direction}.jpg"
        if not path.exists() or path.stat().st_size <= 0:
            return None
        paths[direction] = str(path)
    return paths
