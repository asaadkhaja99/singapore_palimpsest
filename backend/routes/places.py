from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.config import get_settings
from backend.integrations.places_grabmaps import GrabMapsProvider
from backend.schemas import PlacePayload

router = APIRouter(prefix="/api/places", tags=["places"])


@router.get("/search", response_model=list[PlacePayload])
async def search_places(q: str = Query(min_length=1), lat: float = 1.3521, lng: float = 103.8198):
    try:
        provider = GrabMapsProvider(get_settings())
        places = await provider.search_by_text(q, lat, lng, max_results=10)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return [PlacePayload.model_validate(place.model_dump()) for place in places]


@router.get("/nearby", response_model=list[PlacePayload])
async def nearby_places(lat: float, lng: float, radius_m: int = 100):
    try:
        provider = GrabMapsProvider(get_settings())
        places = await provider.nearby(lat, lng, radius_m=radius_m, max_results=20)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return [PlacePayload.model_validate(place.model_dump()) for place in places]
