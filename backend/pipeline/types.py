from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Direction = Literal["N", "E", "S", "W"]
Confidence = Literal["high", "medium", "low", "insufficient"]


class StreetLevelCapture(BaseModel):
    provider: str = "kartaview"
    requested_lat: float
    requested_lng: float
    requested_heading_deg: float
    fov_deg: int = 90
    pitch_deg: int = 0
    photo_id: str
    sequence_id: str | None = None
    source_lat: float
    source_lng: float
    source_heading_deg: float | None = None
    source_capture_date: str | None = None
    source_image_path: str
    reference_crop_paths: dict[Direction, str]
    projection: str | None = None
    available: bool = True
    imagery_license: str = "CC BY-SA 4.0"
    imagery_attribution: str = "KartaView/OpenStreetCam contributors"


class FrameLandmarkDetection(BaseModel):
    bbox_2d: list[int] = Field(min_length=4, max_length=4)
    label: str
    architectural_style: str = ""
    frame_position: Literal["foreground", "middleground", "background"] = "middleground"
    detection_confidence: Literal["high", "medium", "low"] = "medium"


class ResolvedLandmark(BaseModel):
    id: str
    detection: FrameLandmarkDetection
    resolved_name: str | None = None
    resolved_address: str | None = None
    resolved_address_number: str | None = None
    resolved_street: str | None = None
    resolved_lat: float | None = None
    resolved_lng: float | None = None
    place_id: str | None = None
    bearing_from_camera_deg: float
    estimated_distance_m: float
    resolution_confidence: Literal["high", "medium", "low", "unresolved"] = "unresolved"
    source: Literal["vision+places", "vision_only", "places_only"] = "vision_only"

    @property
    def display_name(self) -> str:
        return self.resolved_name or self.detection.label


class FrameInventory(BaseModel):
    capture: StreetLevelCapture
    direction: Direction = "N"
    landmarks: list[ResolvedLandmark]


class ResearchDump(BaseModel):
    landmark_id: str
    landmark_name: str
    era: int
    text: str
    sources: list[str] = []
    historical_reference_image_url: str | None = None


class VisualFact(BaseModel):
    fact: str
    source_url: str | None = None
    confidence: Literal["high", "medium", "low"] = "medium"


class LandmarkEraVisualFacts(BaseModel):
    landmark_id: str
    landmark_name: str
    era: int
    era_label: str
    overall_confidence: Confidence = "insufficient"
    existed_in_era: bool = True
    appearance: list[VisualFact] = []
    architectural_details: list[VisualFact] = []
    signage: list[VisualFact] = []
    surrounding_context: list[VisualFact] = []
    distinctive_features: list[VisualFact] = []
    explicitly_absent: list[VisualFact] = []
    sources_cited: list[str] = []
    historical_reference_image_url: str | None = None


class GateDecision(BaseModel):
    proceed: bool
    reason: str
    eras_to_generate: list[int]
    landmarks_to_ground: list[str]


class NodePlan(BaseModel):
    order_index: int
    lat: float
    lng: float
    capture: StreetLevelCapture
    inventory_by_direction: dict[Direction, FrameInventory] = {}
