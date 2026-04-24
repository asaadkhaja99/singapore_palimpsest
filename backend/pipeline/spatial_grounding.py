from __future__ import annotations

import structlog

from backend.ids import new_id
from backend.integrations.gemini_client import GeminiClient, GeminiUnavailable
from backend.integrations.places import Place, PlacesProvider
from backend.pipeline.geometry import (
    DIRECTION_HEADINGS,
    bearing_between_deg,
    bbox_center_bearing,
    frame_distance_m,
    haversine_m,
    is_named,
    project_point,
    signed_bearing_offset_deg,
)
from backend.pipeline.types import (
    FrameInventory,
    FrameLandmarkDetection,
    ResolvedLandmark,
    StreetLevelCapture,
)

log = structlog.get_logger(__name__)


DETECTION_PROMPT = """
Identify visible buildings and structures in this street-level image from Singapore.
Return only real visible structures, named landmarks when legible/recognizable, and distinct shophouse/building facades.
Do not infer places outside the frame.
For each structure return bbox_2d as [y0, x0, y1, x1] normalized 0-1000, a concise label,
architectural_style, frame_position, and detection_confidence.
"""


async def detect_landmarks(
    gemini: GeminiClient,
    image_path: str,
) -> list[FrameLandmarkDetection]:
    try:
        result = await gemini.generate_json(
            model=gemini.vision_model,
            prompt=DETECTION_PROMPT,
            image_paths=[image_path],
            response_schema=list[FrameLandmarkDetection],
        )
    except GeminiUnavailable:
        return []
    except Exception as exc:
        log.warning(
            "spatial_grounding_detection_failed",
            model=gemini.vision_model,
            image_path=image_path,
            error=str(exc),
        )
        return []
    if isinstance(result, list):
        return [FrameLandmarkDetection.model_validate(item) for item in result]
    return []


async def ground_frame(
    *,
    capture: StreetLevelCapture,
    direction: str,
    places: PlacesProvider,
    gemini: GeminiClient,
) -> FrameInventory:
    if gemini.skip_vision_detection:
        return await _ground_from_nearby_places(capture=capture, direction=direction, places=places)

    image_path = capture.reference_crop_paths[direction]
    detections = await detect_landmarks(gemini, image_path)
    landmarks: list[ResolvedLandmark] = []
    camera_heading = DIRECTION_HEADINGS[direction]
    for det in detections:
        bearing = bbox_center_bearing(camera_heading, capture.fov_deg, det.bbox_2d)
        distance = frame_distance_m(det.frame_position)
        projected_lat, projected_lng = project_point(capture.requested_lat, capture.requested_lng, bearing, distance)
        resolved: Place | None = None
        source = "vision_only"
        confidence = "unresolved"
        max_resolution_distance = max(100.0, distance * 3)
        if is_named(det.label):
            candidates = await _safe_places_text(places, det.label, capture.requested_lat, capture.requested_lng)
            resolved = _pick_best_by_distance(candidates, projected_lat, projected_lng, max_resolution_distance)
            source = "vision+places" if resolved else "vision_only"
            confidence = "high" if resolved else "medium"
        else:
            candidates = await _safe_places_position(places, projected_lat, projected_lng)
            resolved = _pick_best_by_distance(candidates, projected_lat, projected_lng, max_resolution_distance)
            source = "places_only" if resolved else "vision_only"
            confidence = "medium" if resolved else "unresolved"

        landmarks.append(
            ResolvedLandmark(
                id=new_id("lm_"),
                detection=det,
                resolved_name=resolved.name if resolved else None,
                resolved_address=resolved.address if resolved else None,
                resolved_address_number=resolved.address_number if resolved else None,
                resolved_street=resolved.street if resolved else None,
                resolved_lat=resolved.lat if resolved else projected_lat,
                resolved_lng=resolved.lng if resolved else projected_lng,
                place_id=resolved.place_id if resolved else None,
                bearing_from_camera_deg=bearing,
                estimated_distance_m=distance,
                resolution_confidence=confidence,
                source=source,
            )
        )
    return FrameInventory(capture=capture, direction=direction, landmarks=landmarks)


async def _ground_from_nearby_places(
    *,
    capture: StreetLevelCapture,
    direction: str,
    places: PlacesProvider,
) -> FrameInventory:
    camera_heading = DIRECTION_HEADINGS[direction]
    candidates = await _safe_nearby_places(places, capture.requested_lat, capture.requested_lng)
    ranked: list[tuple[float, float, Place]] = []
    for place in candidates:
        distance = place.distance_m
        if distance is None:
            distance = haversine_m(capture.requested_lat, capture.requested_lng, place.lat, place.lng)
        bearing = bearing_between_deg(capture.requested_lat, capture.requested_lng, place.lat, place.lng)
        offset = abs(signed_bearing_offset_deg(bearing, camera_heading))
        ranked.append((0 if offset <= 80 else 1, distance, place))
    ranked.sort(key=lambda item: (item[0], item[1]))
    selected = [place for _, _, place in ranked[:6]]

    landmarks: list[ResolvedLandmark] = []
    for place in selected:
        distance = place.distance_m
        if distance is None:
            distance = haversine_m(capture.requested_lat, capture.requested_lng, place.lat, place.lng)
        bearing = bearing_between_deg(capture.requested_lat, capture.requested_lng, place.lat, place.lng)
        offset = signed_bearing_offset_deg(bearing, camera_heading)
        frame_position = _frame_position_from_distance(distance)
        landmarks.append(
            ResolvedLandmark(
                id=new_id("lm_"),
                detection=FrameLandmarkDetection(
                    bbox_2d=_synthetic_bbox(offset, frame_position),
                    label=place.name,
                    architectural_style=", ".join(place.categories[:3]),
                    frame_position=frame_position,
                    detection_confidence="medium",
                ),
                resolved_name=place.name,
                resolved_address=place.address,
                resolved_address_number=place.address_number,
                resolved_street=place.street,
                resolved_lat=place.lat,
                resolved_lng=place.lng,
                place_id=place.place_id,
                bearing_from_camera_deg=bearing,
                estimated_distance_m=distance,
                resolution_confidence="high" if distance <= 125 else "medium",
                source="places_only",
            )
        )
    return FrameInventory(capture=capture, direction=direction, landmarks=landmarks)


async def _safe_places_text(places: PlacesProvider, query: str, lat: float, lng: float) -> list[Place]:
    try:
        return await places.search_by_text(query, lat, lng, max_results=3)
    except Exception:
        return []


async def _safe_places_position(places: PlacesProvider, lat: float, lng: float) -> list[Place]:
    try:
        return await places.search_by_position(lat, lng, max_results=3)
    except Exception:
        return []


async def _safe_nearby_places(places: PlacesProvider, lat: float, lng: float) -> list[Place]:
    try:
        return await places.nearby(lat, lng, radius_m=175, max_results=12)
    except Exception:
        return await _safe_places_position(places, lat, lng)


def _pick_best_by_distance(
    candidates: list[Place],
    target_lat: float,
    target_lng: float,
    max_distance_m: float,
) -> Place | None:
    nearby = [
        (haversine_m(target_lat, target_lng, candidate.lat, candidate.lng), candidate)
        for candidate in candidates
    ]
    nearby = [(distance, candidate) for distance, candidate in nearby if distance <= max_distance_m]
    if not nearby:
        return None
    nearby.sort(key=lambda item: item[0])
    place = nearby[0][1]
    place.distance_m = nearby[0][0]
    return place


def _frame_position_from_distance(distance_m: float) -> str:
    if distance_m <= 20:
        return "foreground"
    if distance_m <= 75:
        return "middleground"
    return "background"


def _synthetic_bbox(offset_deg: float, frame_position: str) -> list[int]:
    x_center = int(500 + max(-45, min(45, offset_deg)) / 90 * 1000)
    width = {"foreground": 260, "middleground": 190, "background": 130}[frame_position]
    y0, y1 = {
        "foreground": (120, 900),
        "middleground": (90, 780),
        "background": (70, 620),
    }[frame_position]
    x0 = max(0, x_center - width // 2)
    x1 = min(1000, x_center + width // 2)
    return [y0, x0, y1, x1]
