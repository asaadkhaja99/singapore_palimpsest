from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session, select

from backend.config import get_settings
from backend.db import get_session
from backend.ids import new_id
from backend.models import FrameLandmark, LandmarkEraFacts, Node, POI, Tour, View
from backend.pipeline.geometry import slugify
from backend.pipeline.orchestrator import run_tour_pipeline
from backend.schemas import (
    NodePayload,
    POIPayload,
    ProgressPayload,
    ResolveTourRequest,
    ResolveTourResponse,
    TourPayload,
    ViewContextPayload,
    FrameLandmarkPayload,
    LandmarkEraLessonPayload,
    PhotoAnchorPayload,
)
from backend.seeds.curated_tours import CURATED_TOURS

router = APIRouter(prefix="/api/tours", tags=["tours"])


@router.post("/resolve", response_model=ResolveTourResponse)
async def resolve_tour(
    request: ResolveTourRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    settings = get_settings()
    name = request.name or "Live Singapore route"
    tour = Tour(
        id=new_id("tour_"),
        slug=slugify(f"{name}-{request.lat:.5f}-{request.lng:.5f}-{int(request.heading_deg)}"),
        name=name,
        center_lat=request.lat,
        center_lng=request.lng,
        camera_heading_deg=request.heading_deg,
        radius_m=request.radius_m,
        eras=settings.default_eras,
        status="pending",
        progress_stage="queued",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(tour)
    session.commit()
    if not settings.gemini_api_key:
        tour.status = "refused"
        tour.refusal_reason = "GEMINI_API_KEY is not configured, so spatial grounding and historical generation cannot run."
        tour.progress_stage = "configuration"
        tour.updated_at = datetime.utcnow()
        session.add(tour)
        session.commit()
        return ResolveTourResponse(tour_id=tour.id, status=tour.status, poll_url=f"/api/tours/{tour.id}")
    background_tasks.add_task(
        run_tour_pipeline,
        tour_id=tour.id,
        lat=request.lat,
        lng=request.lng,
        heading_deg=request.heading_deg,
        radius_m=request.radius_m,
    )
    return ResolveTourResponse(tour_id=tour.id, status=tour.status, poll_url=f"/api/tours/{tour.id}")


@router.get("/curated")
async def curated_tours(session: Session = Depends(get_session)):
    ready = session.exec(select(Tour).where(Tour.is_curated == True)).all()  # noqa: E712
    ready_payloads = [
        _curated_tour_summary(session, tour)
        for tour in ready
    ]
    seeds = [
        _curated_seed_summary(session, seed)
        for seed in CURATED_TOURS
    ]
    return {"ready": ready_payloads, "seeds": seeds}


@router.post("/curated/{slug}/resolve", response_model=ResolveTourResponse)
async def resolve_curated_tour(
    slug: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    seed = next((item for item in CURATED_TOURS if item["slug"] == slug), None)
    if seed is None:
        raise HTTPException(status_code=404, detail="Curated tour seed not found")
    seed_eras = seed.get("eras", get_settings().default_eras)
    cached = _cached_curated_tour(session, slug, seed_eras, require_complete=get_settings().curated_cache_only)
    if cached is not None:
        return ResolveTourResponse(tour_id=cached.id, status=cached.status, poll_url=f"/api/tours/{cached.id}")
    if get_settings().curated_cache_only:
        raise HTTPException(
            status_code=409,
            detail="This curated route is not fully cached locally. Use live pick to run generation, or pre-render it first.",
        )
    request = ResolveTourRequest(
        lat=seed["center_lat"],
        lng=seed["center_lng"],
        radius_m=seed["radius_m"],
        heading_deg=seed["camera_heading_deg"],
        name=seed["name"],
    )
    response = await resolve_tour(request, background_tasks, session)
    tour = session.get(Tour, response.tour_id)
    if tour:
        tour.is_curated = True
        tour.slug = seed["slug"]
        tour.eras = seed_eras
        session.add(tour)
        session.commit()
    return response


def _cached_curated_tour(
    session: Session,
    slug: str,
    eras: list[int],
    *,
    require_complete: bool = False,
) -> Tour | None:
    tours = session.exec(
        select(Tour)
        .where(Tour.slug == slug, Tour.is_curated == True)  # noqa: E712
        .order_by(Tour.created_at.desc())
    ).all()
    exact_tours = [tour for tour in tours if tour.eras == eras]
    if require_complete:
        exact_tours = [tour for tour in exact_tours if _is_tour_cache_complete(session, tour)]
        fallback_tours = [tour for tour in tours if _is_tour_cache_complete(session, tour)]
    else:
        fallback_tours = tours
    preferred_statuses = ("ready", "generating", "researching", "grounding", "pending")
    for status in preferred_statuses:
        for tour in exact_tours:
            if tour.status == status:
                return tour
    for status in preferred_statuses:
        for tour in fallback_tours:
            if tour.status == status:
                return tour
    return None


def _curated_seed_summary(session: Session, seed: dict) -> dict:
    eras = seed.get("eras", get_settings().default_eras)
    cached = _cached_curated_tour(session, seed["slug"], eras, require_complete=True)
    latest = _latest_curated_tour(session, seed["slug"], eras)
    count_tour = latest or cached
    view_count, expected_view_count = _view_counts(session, count_tour) if count_tour else (0, 0)
    reported_eras = cached.eras if cached else eras
    return {
        "id": seed["slug"],
        "name": seed["name"],
        "status": "seed",
        "lat": seed["center_lat"],
        "lng": seed["center_lng"],
        "heading_deg": seed["camera_heading_deg"],
        "eras": reported_eras,
        "demo_role": seed.get("demo_role"),
        "coverage_note": seed.get("coverage_note"),
        "photo_anchors": seed.get("photo_anchors", []),
        "ready_tour_id": cached.id if cached else None,
        "cache_status": "ready" if cached else (latest.status if latest else "missing"),
        "cached_view_count": view_count,
        "expected_view_count": expected_view_count,
    }


def _curated_tour_summary(session: Session, tour: Tour) -> dict:
    view_count, expected_view_count = _view_counts(session, tour)
    complete = _is_tour_cache_complete(session, tour)
    return {
        "id": tour.id,
        "slug": tour.slug,
        "name": tour.name,
        "status": tour.status,
        "lat": tour.center_lat,
        "lng": tour.center_lng,
        "heading_deg": tour.camera_heading_deg,
        "eras": tour.eras,
        "photo_anchors": _photo_anchors_for_slug(tour.slug),
        "cache_status": "ready" if complete else tour.status,
        "cached_view_count": view_count,
        "expected_view_count": expected_view_count,
    }


def _latest_curated_tour(session: Session, slug: str, eras: list[int]) -> Tour | None:
    tours = session.exec(
        select(Tour)
        .where(Tour.slug == slug, Tour.is_curated == True)  # noqa: E712
        .order_by(Tour.created_at.desc())
    ).all()
    return next((tour for tour in tours if tour.eras == eras), None)


def _view_counts(session: Session, tour: Tour | None) -> tuple[int, int]:
    if tour is None:
        return 0, 0
    nodes = session.exec(select(Node).where(Node.tour_id == tour.id)).all()
    if not nodes:
        return 0, 0
    views = session.exec(select(View).where(View.node_id.in_([node.id for node in nodes]))).all()
    expected = len(nodes) * len(tour.eras) * 4
    return sum(1 for view in views if _is_view_usable(view)), expected


def _is_tour_cache_complete(session: Session, tour: Tour) -> bool:
    if tour.status != "ready":
        return False
    nodes = session.exec(select(Node).where(Node.tour_id == tour.id)).all()
    if not nodes:
        return False
    expected_keys = {
        (node.id, era, direction)
        for node in nodes
        for era in tour.eras
        for direction in ("N", "E", "S", "W")
    }
    views = session.exec(select(View).where(View.node_id.in_([node.id for node in nodes]))).all()
    actual_keys = {(view.node_id, view.era, view.direction) for view in views if _is_view_usable(view)}
    return expected_keys.issubset(actual_keys)


def _view_file_exists(view: View) -> bool:
    path = Path(view.image_path)
    if path.is_absolute():
        return path.exists()
    return path.exists() or (Path.cwd() / path).exists()


def _is_view_usable(view: View) -> bool:
    if not _view_file_exists(view):
        return False
    path = Path(view.image_path)
    if not path.is_absolute() and not path.exists():
        path = Path.cwd() / path
    try:
        head = path.read_bytes()[:8192]
    except OSError:
        return False
    blocked = (b"Generation failed", b"RESOURCE_EXHAUSTED", b"spending cap")
    return not any(marker in head for marker in blocked)


@router.get("/{tour_id}", response_model=TourPayload)
async def get_tour(tour_id: str, session: Session = Depends(get_session)):
    tour = session.get(Tour, tour_id)
    if tour is None:
        raise HTTPException(status_code=404, detail="Tour not found")
    return _tour_payload(session, tour)


def _tour_payload(session: Session, tour: Tour) -> TourPayload:
    progress = None
    if tour.status not in {"ready", "refused", "failed"}:
        progress = ProgressPayload(
            stage=tour.progress_stage,
            current=tour.progress_current,
            total=tour.progress_total,
        )
    nodes = session.exec(select(Node).where(Node.tour_id == tour.id).order_by(Node.order_index)).all()
    pois = session.exec(select(POI).where(POI.tour_id == tour.id)).all()
    node_payloads: list[NodePayload] = []
    for node in nodes:
        views = session.exec(select(View).where(View.node_id == node.id)).all()
        landmarks = session.exec(select(FrameLandmark).where(FrameLandmark.node_id == node.id)).all()
        facts_by_landmark = _facts_by_landmark(session, landmarks)
        views_by_era: dict[str, dict[str, str]] = {}
        view_contexts: dict[str, dict[str, ViewContextPayload]] = {}
        for view in views:
            if not _is_view_usable(view):
                continue
            views_by_era.setdefault(str(view.era), {})[view.direction] = _img_url(view.image_path)
            view_contexts.setdefault(str(view.era), {})[view.direction] = ViewContextPayload(
                model_used=view.model_used,
                grounded_landmark_ids=view.landmarks_grounded,
                prompt_excerpt=_prompt_excerpt(view.prompt_used),
            )
        node_payloads.append(
            NodePayload(
                id=node.id,
                order_index=node.order_index,
                lat=node.lat,
                lng=node.lng,
                neighbors=node.neighbors,
                views=views_by_era,
                reference_crops={key: _img_url(value) for key, value in node.reference_crop_paths.items()},
                landmarks=[
                    FrameLandmarkPayload(
                        id=landmark.id,
                        name=landmark.name,
                        address=landmark.address,
                        address_number=landmark.address_number,
                        street=landmark.street,
                        lat=landmark.lat,
                        lng=landmark.lng,
                        frame_position=landmark.frame_position,
                        bearing_from_camera_deg=landmark.bearing_from_camera_deg,
                        estimated_distance_m=landmark.estimated_distance_m,
                        identification_confidence=landmark.identification_confidence,
                        source=landmark.source,
                        place_id=landmark.place_id,
                        era_facts={
                            str(fact.era): _lesson_from_fact(fact)
                            for fact in facts_by_landmark.get(landmark.id, [])
                        },
                    )
                    for landmark in _sorted_landmarks(landmarks)
                ],
                view_contexts=view_contexts,
                source_photo_id=node.source_photo_id,
                source_provider=node.source_provider,
                source_capture_date=node.source_capture_date,
                source_lat=node.source_lat,
                source_lng=node.source_lng,
                source_heading_deg=node.source_heading_deg,
            )
        )
    return TourPayload(
        id=tour.id,
        name=tour.name,
        status=tour.status,
        refusal_reason=tour.refusal_reason,
        failure_reason=tour.failure_reason,
        progress=progress,
        eras=tour.eras,
        photo_anchors=_photo_anchors_for_slug(tour.slug),
        nodes=node_payloads,
        pois=[
            POIPayload(
                id=poi.id,
                name=poi.name,
                lat=poi.lat,
                lng=poi.lng,
                historical_context=poi.historical_context,
                visible_from_node_ids=poi.visible_from_node_ids,
            )
            for poi in pois
        ],
        imagery_attribution=tour.imagery_attribution,
        generated_image_notice=tour.generated_image_notice,
    )


def _img_url(path: str | None) -> str:
    if not path:
        return ""
    settings = get_settings()
    img_root = settings.palimpsest_img_dir.resolve()
    resolved = Path(path).resolve()
    try:
        return "/img/" + str(resolved.relative_to(img_root)).replace("\\", "/")
    except ValueError:
        return path


def _prompt_excerpt(prompt: str, max_chars: int = 2200) -> str:
    prompt = prompt.strip()
    if len(prompt) <= max_chars:
        return prompt
    return f"{prompt[:max_chars].rstrip()}..."


def _sorted_landmarks(landmarks: list[FrameLandmark]) -> list[FrameLandmark]:
    return sorted(landmarks, key=lambda item: (item.estimated_distance_m, item.name))


def _photo_anchors_for_slug(slug: str) -> list[PhotoAnchorPayload]:
    seed = next((item for item in CURATED_TOURS if item["slug"] == slug), None)
    if seed is None:
        return []
    return [PhotoAnchorPayload(**anchor) for anchor in seed.get("photo_anchors", [])]


def _facts_by_landmark(
    session: Session,
    landmarks: list[FrameLandmark],
) -> dict[str, list[LandmarkEraFacts]]:
    if not landmarks:
        return {}
    ids = [landmark.id for landmark in landmarks]
    facts = session.exec(select(LandmarkEraFacts).where(LandmarkEraFacts.landmark_id.in_(ids))).all()
    grouped: dict[str, list[LandmarkEraFacts]] = {}
    for fact in facts:
        grouped.setdefault(fact.landmark_id, []).append(fact)
    for values in grouped.values():
        values.sort(key=lambda item: item.era)
    return grouped


def _lesson_from_fact(fact: LandmarkEraFacts) -> LandmarkEraLessonPayload:
    payload = fact.facts_json or {}
    highlights = _fact_highlights(payload)
    return LandmarkEraLessonPayload(
        era=fact.era,
        era_label=str(payload.get("era_label") or fact.era),
        overall_confidence=fact.overall_confidence,
        existed_in_era=bool(payload.get("existed_in_era", True)),
        highlights=highlights,
        sources=fact.sources_cited[:6],
    )


def _fact_highlights(payload: dict, limit: int = 4) -> list[str]:
    highlights: list[str] = []
    for key in (
        "appearance",
        "architectural_details",
        "signage",
        "surrounding_context",
        "distinctive_features",
    ):
        values = payload.get(key) or []
        for value in values:
            if isinstance(value, dict):
                text = value.get("fact")
            else:
                text = str(value)
            if text:
                highlights.append(str(text))
            if len(highlights) >= limit:
                return highlights
    return highlights
