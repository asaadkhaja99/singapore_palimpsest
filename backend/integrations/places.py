from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class Place(BaseModel):
    name: str
    address: str | None = None
    address_number: str | None = None
    street: str | None = None
    lat: float
    lng: float
    categories: list[str] = []
    distance_m: float | None = None
    place_id: str


class RouteWaypoint(BaseModel):
    lat: float
    lng: float
    distance_from_start_m: float


class PlacesProvider(Protocol):
    async def search_by_text(
        self, query: str, bias_lat: float, bias_lng: float, max_results: int = 5
    ) -> list[Place]: ...

    async def search_by_position(self, lat: float, lng: float, max_results: int = 5) -> list[Place]: ...

    async def nearby(self, lat: float, lng: float, radius_m: int, max_results: int = 20) -> list[Place]: ...

    async def walking_route(
        self, start_lat: float, start_lng: float, end_lat: float, end_lng: float
    ) -> list[RouteWaypoint]: ...
