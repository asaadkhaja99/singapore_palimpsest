from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session, select

from backend.config import get_settings
from backend.db import get_session
from backend.ids import new_id
from backend.models import Node, POI, Tour, View
from backend.pipeline.geometry import slugify
from backend.pipeline.orchestrator import run_tour_pipeline
from backend.schemas import (
    NodePayload,
    POIPayload,
    ProgressPayload,
    ResolveTourRequest,
    ResolveTourResponse,
    TourPayload,
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
        {
            "id": tour.id,
            "name": tour.name,
            "status": tour.status,
            "lat": tour.center_lat,
            "lng": tour.center_lng,
            "heading_deg": tour.camera_heading_deg,
        }
        for tour in ready
    ]
    seeds = [
        {
            "id": seed["slug"],
            "name": seed["name"],
            "status": "seed",
            "lat": seed["center_lat"],
            "lng": seed["center_lng"],
            "heading_deg": seed["camera_heading_deg"],
        }
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
        tour.eras = seed.get("eras", get_settings().default_eras)
        session.add(tour)
        session.commit()
    return response


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
        views_by_era: dict[str, dict[str, str]] = {}
        for view in views:
            views_by_era.setdefault(str(view.era), {})[view.direction] = _img_url(view.image_path)
        node_payloads.append(
            NodePayload(
                id=node.id,
                order_index=node.order_index,
                lat=node.lat,
                lng=node.lng,
                neighbors=node.neighbors,
                views=views_by_era,
                reference_crops={key: _img_url(value) for key, value in node.reference_crop_paths.items()},
                source_photo_id=node.source_photo_id,
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
