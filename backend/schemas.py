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
    openai_configured: bool
    research_provider: str
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


class LandmarkEraLessonPayload(BaseModel):
    era: int
    era_label: str
    overall_confidence: str
    existed_in_era: bool
    highlights: list[str] = []
    sources: list[str] = []


class FrameLandmarkPayload(BaseModel):
    id: str
    name: str
    address: str | None = None
    address_number: str | None = None
    street: str | None = None
    lat: float | None = None
    lng: float | None = None
    frame_position: str
    bearing_from_camera_deg: float
    estimated_distance_m: float
    identification_confidence: str
    source: str
    place_id: str | None = None
    era_facts: dict[str, LandmarkEraLessonPayload] = Field(default_factory=dict)


class ViewContextPayload(BaseModel):
    model_used: str
    grounded_landmark_ids: list[str]
    prompt_excerpt: str


class PhotoAnchorPayload(BaseModel):
    era: int
    label: str
    credit: str | None = None


class NodePayload(BaseModel):
    id: str
    order_index: int
    lat: float
    lng: float
    neighbors: dict
    views: dict
    reference_crops: dict
    landmarks: list[FrameLandmarkPayload] = []
    view_contexts: dict[str, dict[str, ViewContextPayload]] = {}
    source_photo_id: str | None = None
    source_provider: str | None = None
    source_capture_date: str | None = None
    source_lat: float | None = None
    source_lng: float | None = None
    source_heading_deg: float | None = None


class TourPayload(BaseModel):
    id: str
    name: str
    status: str
    refusal_reason: str | None = None
    failure_reason: str | None = None
    progress: ProgressPayload | None = None
    eras: list[int] = []
    photo_anchors: list[PhotoAnchorPayload] = []
    nodes: list[NodePayload] = []
    pois: list[POIPayload] = []
    imagery_attribution: str | None = None
    generated_image_notice: str | None = None
