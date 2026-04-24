from __future__ import annotations

import math
from typing import Any

import httpx

from backend.config import Settings
from backend.integrations.places import Place, RouteWaypoint
from backend.pipeline.geometry import haversine_m


def _first(value: Any, *keys: str) -> Any:
    if not isinstance(value, dict):
        return None
    for key in keys:
        if key in value and value[key] is not None:
            return value[key]
    return None


def _walk_candidates(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("places", "results", "pois", "items", "data", "currentPageItems"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _walk_candidates(value)
            if nested:
                return nested
    return []


def _location_from_item(item: dict[str, Any]) -> tuple[float | None, float | None]:
    loc = _first(item, "location", "coordinate", "coordinates", "geometry")
    if isinstance(loc, dict):
        lat = _first(loc, "lat", "latitude")
        lng = _first(loc, "lng", "lon", "longitude")
        if lat is None and isinstance(loc.get("location"), dict):
            lat = _first(loc["location"], "lat", "latitude")
            lng = _first(loc["location"], "lng", "lon", "longitude")
        if lat is not None and lng is not None:
            return float(lat), float(lng)
    lat = _first(item, "lat", "latitude")
    lng = _first(item, "lng", "lon", "longitude")
    if lat is not None and lng is not None:
        return float(lat), float(lng)
    return None, None


def _parse_place(item: dict[str, Any], query_lat: float | None = None, query_lng: float | None = None) -> Place | None:
    lat, lng = _location_from_item(item)
    if lat is None or lng is None:
        return None
    name = str(_first(item, "name", "title", "poiName", "displayName") or "Unnamed place")
    address = _first(item, "formatted_address", "formattedAddress", "address", "vicinity")
    address_number = _first(item, "address_number", "addressNumber", "houseNumber")
    street = _first(item, "street", "streetName", "road")
    categories_raw = _first(item, "categories", "category", "types", "tags") or []
    if isinstance(categories_raw, str):
        categories = [categories_raw]
    else:
        categories = [str(category) for category in categories_raw if category]
    distance = _first(item, "distance_m", "distance", "distanceMeters")
    computed_distance = haversine_m(query_lat, query_lng, lat, lng) if query_lat is not None and query_lng is not None else None
    if distance is not None:
        distance = float(distance)
        if computed_distance is not None and distance < computed_distance / 10:
            distance *= 1000
    elif computed_distance is not None:
        distance = computed_distance
    place_id = str(_first(item, "place_id", "placeId", "poi_id", "poiId", "id") or f"grab:{lat:.6f},{lng:.6f}:{name}")
    return Place(
        name=name,
        address=str(address) if address is not None else None,
        address_number=str(address_number) if address_number is not None else None,
        street=str(street) if street is not None else None,
        lat=lat,
        lng=lng,
        categories=categories,
        distance_m=float(distance) if distance is not None else None,
        place_id=place_id,
    )


def decode_polyline(encoded: str, precision: int = 6) -> list[tuple[float, float]]:
    coordinates: list[tuple[float, float]] = []
    index = lat = lng = 0
    factor = 10**precision
    while index < len(encoded):
        result = shift = 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lat += ~(result >> 1) if result & 1 else result >> 1
        result = shift = 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lng += ~(result >> 1) if result & 1 else result >> 1
        coordinates.append((lat / factor, lng / factor))
    return coordinates


class GrabMapsProvider:
    def __init__(self, settings: Settings):
        if not settings.grabmaps_api_key:
            raise RuntimeError("GRABMAPS_API_KEY is required for GrabMapsProvider")
        self.base_url = settings.grabmaps_base_url.rstrip("/")
        self.api_key = settings.grabmaps_api_key

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}

    async def _get(self, path: str, params: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self.base_url}{path}", params=params, headers=self._headers)
            response.raise_for_status()
            return response.json()

    async def search_by_text(
        self, query: str, bias_lat: float, bias_lng: float, max_results: int = 5
    ) -> list[Place]:
        payload = await self._get(
            "/api/v1/maps/poi/v1/search",
            {
                "keyword": query,
                "country": "SGP",
                "location": f"{bias_lat},{bias_lng}",
                "limit": str(max_results),
            },
        )
        return [
            place
            for item in _walk_candidates(payload)
            if (place := _parse_place(item, bias_lat, bias_lng)) is not None
        ][:max_results]

    async def search_by_position(self, lat: float, lng: float, max_results: int = 5) -> list[Place]:
        return await self.nearby(lat, lng, radius_m=75, max_results=max_results)

    async def nearby(self, lat: float, lng: float, radius_m: int, max_results: int = 20) -> list[Place]:
        payload = await self._get(
            "/api/v1/maps/place/v2/nearby",
            {
                "location": f"{lat},{lng}",
                "radius": f"{max(radius_m, 1) / 1000:.3f}",
                "limit": str(max_results),
                "rankBy": "distance",
                "language": "en",
            },
        )
        return [
            place for item in _walk_candidates(payload) if (place := _parse_place(item, lat, lng)) is not None
        ][:max_results]

    async def walking_route(
        self, start_lat: float, start_lng: float, end_lat: float, end_lng: float
    ) -> list[RouteWaypoint]:
        params = [
            ("coordinates", f"{start_lng},{start_lat}"),
            ("coordinates", f"{end_lng},{end_lat}"),
            ("profile", "walking"),
            ("overview", "full"),
            ("steps", "true"),
            ("geometries", "polyline6"),
        ]
        payload = await self._get("/api/v1/maps/eta/v1/direction", params)
        route = (payload.get("routes") or [{}])[0]
        coords: list[tuple[float, float]] = []
        geometry = route.get("geometry")
        if isinstance(geometry, str) and geometry:
            coords = decode_polyline(geometry, precision=6)
        elif isinstance(geometry, dict) and isinstance(geometry.get("coordinates"), list):
            coords = [(float(lat), float(lng)) for lng, lat in geometry["coordinates"]]
        if not coords:
            coords = [(start_lat, start_lng), (end_lat, end_lng)]

        waypoints: list[RouteWaypoint] = []
        total = 0.0
        previous: tuple[float, float] | None = None
        for lat, lng in coords:
            if previous:
                total += haversine_m(previous[0], previous[1], lat, lng)
            waypoints.append(RouteWaypoint(lat=lat, lng=lng, distance_from_start_m=total))
            previous = (lat, lng)
        return waypoints
