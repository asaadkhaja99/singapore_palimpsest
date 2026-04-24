from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlmodel import Session

from backend.config import get_settings
from backend.db import engine
from backend.ids import new_id
from backend.integrations.gemini_client import GeminiClient
from backend.integrations.kartaview import KartaViewProvider
from backend.integrations.places_grabmaps import GrabMapsProvider
from backend.models import FrameLandmark, LandmarkEraFacts, Node, POI, Tour, View
from backend.pipeline.extractor import extract_visual_facts
from backend.pipeline.gate import decide_gate
from backend.pipeline.geometry import is_named
from backend.pipeline.image_generator import ANCHOR_MODEL, FAST_MODEL, generate_view_image
from backend.pipeline.node_planner import plan_nodes
from backend.pipeline.poi_enrichment import enrich_poi
from backend.pipeline.prompt_synth import synth_prompt
from backend.pipeline.research_agent import research_landmark_era
from backend.pipeline.spatial_grounding import ground_frame
from backend.pipeline.types import Direction, LandmarkEraVisualFacts, NodePlan, ResolvedLandmark, VisualFact


DIRECTIONS: tuple[Direction, ...] = ("N", "E", "S", "W")


@dataclass
class ViewGenerationResult:
    node_id: str
    era: int
    direction: Direction
    image_path: str
    prompt: str
    model: str
    grounded_ids: list[str]


async def run_tour_pipeline(
    *,
    tour_id: str,
    lat: float,
    lng: float,
    heading_deg: float,
    radius_m: int,
) -> None:
    settings = get_settings()
    gemini = GeminiClient(settings)
    with Session(engine) as session:
        tour = session.get(Tour, tour_id)
        if tour is None:
            return
        try:
            _status(session, tour, "grounding", "planning nodes", 0, settings.default_node_count)
            places = GrabMapsProvider(settings)
            street_level = KartaViewProvider(settings)
            node_plans = await plan_nodes(
                settings=settings,
                places=places,
                street_level=street_level,
                lat=lat,
                lng=lng,
                heading_deg=heading_deg,
                radius_m=radius_m,
                count=settings.default_node_count,
            )
            if not node_plans:
                _refuse(session, tour, "No usable KartaView/OpenStreetCam imagery was found near this route.")
                return

            total_grounding = len(node_plans) * len(DIRECTIONS)
            grounded = 0
            for plan in node_plans:
                for direction in DIRECTIONS:
                    inventory = await ground_frame(
                        capture=plan.capture,
                        direction=direction,
                        places=places,
                        gemini=gemini,
                    )
                    plan.inventory_by_direction[direction] = inventory
                    grounded += 1
                    _status(session, tour, "grounding", "spatial grounding", grounded, total_grounding)

            landmarks = _landmarks_for_research(node_plans)
            if len(landmarks) < 2:
                _refuse(
                    session,
                    tour,
                    "We could not identify at least two grounded visible structures in the street-level imagery.",
                )
                return

            facts: list[LandmarkEraVisualFacts] = []
            total_research = len(landmarks) * len(tour.eras)
            _status(session, tour, "researching", "landmark research", 0, total_research)
            if settings.fast_landmark_research:
                facts = _fast_facts(landmarks, tour.eras)
                _status(session, tour, "researching", "fast landmark facts", total_research, total_research)
            else:
                completed_research = 0
                for landmark in landmarks:
                    for era in tour.eras:
                        if era >= 2020:
                            facts.append(_current_day_fact(landmark, era))
                        else:
                            dump = await research_landmark_era(gemini, landmark, era)
                            facts.append(await extract_visual_facts(gemini, dump))
                        completed_research += 1
                        _status(session, tour, "researching", "landmark research", completed_research, total_research)

            gate = decide_gate(landmarks, facts, tour.eras)
            if not gate.proceed:
                _refuse(session, tour, gate.reason)
                return

            node_ids = _persist_nodes_and_landmarks(session, tour, node_plans)
            _persist_facts(session, facts)

            await _generate_views_concurrently(
                session=session,
                tour=tour,
                settings=settings,
                gemini=gemini,
                node_plans=node_plans,
                node_ids=node_ids,
                facts=facts,
                eras=gate.eras_to_generate,
            )

            await _persist_pois(session, tour, node_plans, facts, gemini)
            tour.status = "ready"
            tour.progress_stage = "ready"
            tour.progress_current = tour.progress_total
            tour.updated_at = datetime.utcnow()
            session.add(tour)
            session.commit()
        except Exception as exc:
            tour.status = "failed"
            tour.failure_reason = str(exc)
            tour.progress_stage = "failed"
            tour.updated_at = datetime.utcnow()
            session.add(tour)
            session.commit()


def _status(session: Session, tour: Tour, status: str, stage: str, current: int, total: int) -> None:
    tour.status = status
    tour.progress_stage = stage
    tour.progress_current = current
    tour.progress_total = total
    tour.updated_at = datetime.utcnow()
    session.add(tour)
    session.commit()


def _refuse(session: Session, tour: Tour, reason: str) -> None:
    tour.status = "refused"
    tour.refusal_reason = reason
    tour.progress_stage = "refused"
    tour.updated_at = datetime.utcnow()
    session.add(tour)
    session.commit()


async def _generate_views_concurrently(
    *,
    session: Session,
    tour: Tour,
    settings,
    gemini: GeminiClient,
    node_plans: list[NodePlan],
    node_ids: dict[int, str],
    facts: list[LandmarkEraVisualFacts],
    eras: list[int],
) -> None:
    total_views = len(eras) * len(node_plans) * len(DIRECTIONS)
    generated = 0
    _status(
        session,
        tour,
        "generating",
        f"image generation, concurrency {settings.image_generation_concurrency}",
        0,
        total_views,
    )

    semaphore = asyncio.Semaphore(max(1, settings.image_generation_concurrency))
    rate_limiter = _StartRateLimiter(settings.image_generation_start_interval_s)
    tasks: list[asyncio.Task[ViewGenerationResult]] = []
    for era in eras:
        for plan in node_plans:
            node_id = node_ids[plan.order_index]
            for direction in DIRECTIONS:
                tasks.append(
                    asyncio.create_task(
                        _generate_one_view(
                            semaphore=semaphore,
                            rate_limiter=rate_limiter,
                            settings=settings,
                            gemini=gemini,
                            tour_id=tour.id,
                            plan=plan,
                            node_id=node_id,
                            facts=facts,
                            era=era,
                            direction=direction,
                        )
                    )
                )

    for task in asyncio.as_completed(tasks):
        result = await task
        session.add(
            View(
                id=new_id("view_"),
                node_id=result.node_id,
                era=result.era,
                direction=result.direction,
                image_path=result.image_path,
                prompt_used=result.prompt,
                reference_view_ids=[],
                streetlevel_reference_used=True,
                model_used=result.model,
                landmarks_grounded=result.grounded_ids,
            )
        )
        session.commit()
        generated += 1
        _status(
            session,
            tour,
            "generating",
            f"image generation, concurrency {settings.image_generation_concurrency}",
            generated,
            total_views,
        )


async def _generate_one_view(
    *,
    semaphore: asyncio.Semaphore,
    rate_limiter: "_StartRateLimiter",
    settings,
    gemini: GeminiClient,
    tour_id: str,
    plan: NodePlan,
    node_id: str,
    facts: list[LandmarkEraVisualFacts],
    era: int,
    direction: Direction,
) -> ViewGenerationResult:
    inventory = plan.inventory_by_direction.get(direction) or plan.inventory_by_direction["N"]
    prompt, historical_refs, grounded_ids = synth_prompt(
        inventory=inventory,
        facts=facts,
        era=era,
        direction=direction,
    )
    reference_crop = plan.capture.reference_crop_paths[direction]
    if era >= 2020:
        return ViewGenerationResult(
            node_id=node_id,
            era=era,
            direction=direction,
            image_path=reference_crop,
            prompt=prompt,
            model="kartaview-reference",
            grounded_ids=grounded_ids,
        )

    model = ANCHOR_MODEL if plan.order_index == 0 and direction == "N" else FAST_MODEL
    refs = [reference_crop, *historical_refs]
    out_path = settings.palimpsest_img_dir / "generated" / tour_id / node_id / f"{era}_{direction}.jpg"
    async with semaphore:
        await rate_limiter.wait()
        image_path = await generate_view_image(
            gemini=gemini,
            prompt=prompt,
            reference_paths=refs[:5],
            out_path=out_path,
            model=model,
        )
    return ViewGenerationResult(
        node_id=node_id,
        era=era,
        direction=direction,
        image_path=image_path,
        prompt=prompt,
        model=model,
        grounded_ids=grounded_ids,
    )


class _StartRateLimiter:
    def __init__(self, interval_s: float):
        self.interval_s = max(0.0, interval_s)
        self._lock = asyncio.Lock()
        self._next_start = 0.0

    async def wait(self) -> None:
        if self.interval_s <= 0:
            return
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            if now < self._next_start:
                await asyncio.sleep(self._next_start - now)
                now = loop.time()
            self._next_start = now + self.interval_s


def _landmarks_for_research(node_plans: list[NodePlan]) -> list[ResolvedLandmark]:
    seen: set[str] = set()
    landmarks: list[ResolvedLandmark] = []
    for plan in node_plans:
        for inventory in plan.inventory_by_direction.values():
            for landmark in inventory.landmarks:
                key = landmark.place_id or landmark.display_name.lower()
                if key in seen:
                    continue
                if landmark.source == "places_only" and not is_named(landmark.display_name):
                    continue
                seen.add(key)
                landmarks.append(landmark)
    resolved = [lm for lm in landmarks if lm.source == "vision+places"]
    rest = [lm for lm in landmarks if lm.source != "vision+places"]
    return [*resolved, *rest][:4]


def _current_day_fact(landmark: ResolvedLandmark, era: int) -> LandmarkEraVisualFacts:
    return LandmarkEraVisualFacts(
        landmark_id=landmark.id,
        landmark_name=landmark.display_name,
        era=era,
        era_label="the present day",
        overall_confidence="high",
        existed_in_era=True,
        appearance=[
            VisualFact(
                fact="The structure is visible in the current-day KartaView/OpenStreetCam reference image.",
                source_url=None,
                confidence="high",
            )
        ],
        sources_cited=["KartaView/OpenStreetCam current-day reference imagery"],
    )


def _fast_facts(landmarks: list[ResolvedLandmark], eras: list[int]) -> list[LandmarkEraVisualFacts]:
    return [_fast_era_fact(landmark, era) for landmark in landmarks for era in eras]


def _fast_era_fact(landmark: ResolvedLandmark, era: int) -> LandmarkEraVisualFacts:
    if era >= 2020:
        return _current_day_fact(landmark, era)

    era_label = f"around {era}"
    street = landmark.resolved_street or "this Singapore street"
    address = landmark.resolved_address or landmark.display_name
    source = "Hackathon fast mode: GrabMaps place identity plus current KartaView/OpenStreetCam reference geometry."
    appearance = [
        VisualFact(
            fact=f"Use the current reference image only for composition and position of {landmark.display_name}; adapt facade materials, signage, vehicles, and street furniture to {era_label}.",
            source_url=None,
            confidence="high",
        ),
        VisualFact(
            fact=f"The scene is set at {address}; keep this landmark in the same approximate bearing and depth within the frame.",
            source_url=None,
            confidence="high",
        ),
    ]
    context = [
        VisualFact(
            fact=_era_context(era, street),
            source_url=None,
            confidence="medium",
        )
    ]
    absent = [
        VisualFact(
            fact="Do not add modern glass towers, modern traffic signals, current-day cars, or contemporary street markings unless they are appropriate for the target era.",
            source_url=None,
            confidence="high",
        )
    ]
    return LandmarkEraVisualFacts(
        landmark_id=landmark.id,
        landmark_name=landmark.display_name,
        era=era,
        era_label=era_label,
        overall_confidence="medium",
        existed_in_era=True,
        appearance=appearance,
        surrounding_context=context,
        explicitly_absent=absent,
        sources_cited=[source],
    )


def _era_context(era: int, street: str) -> str:
    if era < 1930:
        return f"{street} should read as an early twentieth-century Singapore streetscape with restrained shopfront signage, older road surfaces, handcarts, rickshaws, and sparse motor traffic."
    if era < 1970:
        return f"{street} should read as a mid-century Singapore streetscape with painted shopfronts, practical commercial signage, tropical wear, bicycles, buses, and modest motor traffic."
    return f"{street} should read as a late twentieth-century Singapore streetscape with older shopfront finishes, denser roadside parking, period cars, practical signage, and fewer contemporary streetscape upgrades."


def _persist_nodes_and_landmarks(session: Session, tour: Tour, node_plans: list[NodePlan]) -> dict[int, str]:
    node_ids: dict[int, str] = {}
    for index, plan in enumerate(node_plans):
        node_ids[index] = new_id("node_")
    for index, plan in enumerate(node_plans):
        node_id = node_ids[index]
        neighbors = {
            "forward": node_ids.get(index + 1),
            "backward": node_ids.get(index - 1),
        }
        node = Node(
            id=node_id,
            tour_id=tour.id,
            order_index=index,
            lat=plan.lat,
            lng=plan.lng,
            neighbors=neighbors,
            source_photo_id=plan.capture.photo_id,
            source_sequence_id=plan.capture.sequence_id,
            source_capture_date=plan.capture.source_capture_date,
            source_lat=plan.capture.source_lat,
            source_lng=plan.capture.source_lng,
            source_heading_deg=plan.capture.source_heading_deg,
            source_image_path=plan.capture.source_image_path,
            reference_crop_paths=plan.capture.reference_crop_paths,
        )
        session.add(node)
        for inventory in plan.inventory_by_direction.values():
            for landmark in inventory.landmarks:
                bbox = landmark.detection.bbox_2d
                session.add(
                    FrameLandmark(
                        id=landmark.id,
                        node_id=node_id,
                        name=landmark.display_name,
                        address=landmark.resolved_address,
                        address_number=landmark.resolved_address_number,
                        street=landmark.resolved_street,
                        lat=landmark.resolved_lat,
                        lng=landmark.resolved_lng,
                        bbox_x0=bbox[1],
                        bbox_y0=bbox[0],
                        bbox_x1=bbox[3],
                        bbox_y1=bbox[2],
                        frame_position=landmark.detection.frame_position,
                        bearing_from_camera_deg=landmark.bearing_from_camera_deg,
                        estimated_distance_m=landmark.estimated_distance_m,
                        identification_confidence=landmark.resolution_confidence,
                        source=landmark.source,
                        place_id=landmark.place_id,
                    )
                )
    session.commit()
    return node_ids


def _persist_facts(session: Session, facts: list[LandmarkEraVisualFacts]) -> None:
    for fact in facts:
        session.add(
            LandmarkEraFacts(
                id=new_id("fact_"),
                landmark_id=fact.landmark_id,
                era=fact.era,
                overall_confidence=fact.overall_confidence,
                facts_json=fact.model_dump(mode="json"),
                sources_cited=fact.sources_cited,
                historical_reference_image_paths=([fact.historical_reference_image_url] if fact.historical_reference_image_url else []),
            )
        )
    session.commit()


async def _persist_pois(
    session: Session,
    tour: Tour,
    node_plans: list[NodePlan],
    facts: list[LandmarkEraVisualFacts],
    gemini: GeminiClient,
) -> None:
    visible: dict[str, tuple[ResolvedLandmark, set[str]]] = {}
    nodes = session.query(Node).filter(Node.tour_id == tour.id).all()
    nodes_by_order = {node.order_index: node for node in nodes}
    for plan in node_plans:
        node = nodes_by_order.get(plan.order_index)
        if not node:
            continue
        for inventory in plan.inventory_by_direction.values():
            for landmark in inventory.landmarks:
                if not landmark.resolved_lat or not landmark.resolved_lng:
                    continue
                key = landmark.place_id or landmark.display_name.lower()
                if key not in visible:
                    visible[key] = (landmark, set())
                visible[key][1].add(node.id)
    for landmark, node_ids in visible.values():
        context = await enrich_poi(gemini=gemini, landmark=landmark, facts=facts)
        session.add(
            POI(
                id=new_id("poi_"),
                tour_id=tour.id,
                name=landmark.display_name,
                lat=landmark.resolved_lat or 0,
                lng=landmark.resolved_lng or 0,
                historical_context=context,
                visible_from_node_ids=sorted(node_ids),
            )
        )
    session.commit()
