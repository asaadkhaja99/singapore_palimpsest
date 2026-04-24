from __future__ import annotations

from pydantic import BaseModel, Field


class ResolveTourRequest(BaseModel):
    lat: float
    lng: float
    radius_m: int = Field(default=100, ge=25, le=500)
    heading_deg: float = Field(default=0, ge=0, lt=360)
    name: str | None = None


class ResolveTourResponse(BaseModel):
    tour_id: str
    status: str
    poll_url: str | None = None


class SystemStatusPayload(BaseModel):
    backend_ready: bool
    grabmaps_configured: bool
    gemini_configured: bool
    kartaview_configured: bool
    full_pipeline_ready: bool
    missing: list[str] = []


class ProgressPayload(BaseModel):
    stage: str | None
    current: int
    total: int


class PlacePayload(BaseModel):
    name: str
    address: str | None = None
    address_number: str | None = None
    street: str | None = None
    lat: float
    lng: float
    categories: list[str] = []
    distance_m: float | None = None
    place_id: str


class POIPayload(BaseModel):
    id: str
    name: str
    lat: float
    lng: float
    historical_context: str
    visible_from_node_ids: list[str]


class NodePayload(BaseModel):
    id: str
    order_index: int
    lat: float
    lng: float
    neighbors: dict
    views: dict
    reference_crops: dict
    source_photo_id: str | None = None


class TourPayload(BaseModel):
    id: str
    name: str
    status: str
    refusal_reason: str | None = None
    failure_reason: str | None = None
    progress: ProgressPayload | None = None
    eras: list[int] = []
    nodes: list[NodePayload] = []
    pois: list[POIPayload] = []
    imagery_attribution: str | None = None
    generated_image_notice: str | None = None
