from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class Tour(SQLModel, table=True):
    id: str = Field(primary_key=True)
    slug: str = Field(index=True)
    name: str
    center_lat: float
    center_lng: float
    camera_heading_deg: float = 0
    radius_m: int = 100
    is_curated: bool = False
    status: str = Field(default="pending", index=True)
    refusal_reason: str | None = None
    failure_reason: str | None = None
    eras: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    progress_stage: str | None = None
    progress_current: int = 0
    progress_total: int = 0
    imagery_attribution: str = (
        "Street-level reference imagery from KartaView/OpenStreetCam contributors, "
        "licensed under CC BY-SA 4.0. Cropped/projected for Palimpsest."
    )
    generated_image_notice: str = (
        "Generated historical scenes use KartaView/OpenStreetCam reference imagery "
        "and cited historical sources."
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Node(SQLModel, table=True):
    id: str = Field(primary_key=True)
    tour_id: str = Field(index=True, foreign_key="tour.id")
    order_index: int
    lat: float
    lng: float
    neighbors: dict = Field(default_factory=dict, sa_column=Column(JSON))

    source_provider: str = "kartaview"
    source_photo_id: str | None = None
    source_sequence_id: str | None = None
    source_capture_date: str | None = None
    source_lat: float | None = None
    source_lng: float | None = None
    source_heading_deg: float | None = None
    source_image_path: str | None = None
    reference_crop_paths: dict = Field(default_factory=dict, sa_column=Column(JSON))
    imagery_license: str = "CC BY-SA 4.0"
    imagery_attribution: str = "KartaView/OpenStreetCam contributors"


class FrameLandmark(SQLModel, table=True):
    id: str = Field(primary_key=True)
    node_id: str = Field(index=True, foreign_key="node.id")
    name: str
    address: str | None = None
    address_number: str | None = None
    street: str | None = None
    lat: float | None = None
    lng: float | None = None
    bbox_x0: int
    bbox_y0: int
    bbox_x1: int
    bbox_y1: int
    frame_position: str
    bearing_from_camera_deg: float
    estimated_distance_m: float
    identification_confidence: str
    source: str
    place_id: str | None = None


class View(SQLModel, table=True):
    id: str = Field(primary_key=True)
    node_id: str = Field(index=True, foreign_key="node.id")
    era: int = Field(index=True)
    direction: str
    image_path: str
    prompt_used: str
    reference_view_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    streetlevel_reference_used: bool = True
    model_used: str
    landmarks_grounded: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class LandmarkEraFacts(SQLModel, table=True):
    id: str = Field(primary_key=True)
    landmark_id: str = Field(index=True, foreign_key="framelandmark.id")
    era: int = Field(index=True)
    overall_confidence: str
    facts_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    sources_cited: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    historical_reference_image_paths: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class POI(SQLModel, table=True):
    id: str = Field(primary_key=True)
    tour_id: str = Field(index=True, foreign_key="tour.id")
    name: str
    lat: float
    lng: float
    historical_context: str
    visible_from_node_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
