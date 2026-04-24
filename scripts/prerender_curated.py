from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path
import sys

from sqlmodel import Session, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import get_settings
from backend.db import engine, init_db
from backend.ids import new_id
from backend.models import Node, Tour, View
from backend.pipeline.orchestrator import run_tour_pipeline
from backend.seeds.curated_tours import CURATED_TOURS


async def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-render curated Palimpsest demo tours.")
    parser.add_argument("--slug", action="append", help="Only render this curated slug. Can be repeated.")
    parser.add_argument("--force", action="store_true", help="Render even when a complete local cache already exists.")
    args = parser.parse_args()

    init_db()
    settings = get_settings()
    for seed in CURATED_TOURS:
        if args.slug and seed["slug"] not in args.slug:
            continue
        with Session(engine) as session:
            cached = _complete_cached_tour(session, seed)
            if cached is not None and not args.force:
                print(f"Skipping {seed['slug']}: complete local cache already exists as {cached.id}")
                continue
            tour = Tour(
                id=new_id("tour_"),
                slug=seed["slug"],
                name=seed["name"],
                center_lat=seed["center_lat"],
                center_lng=seed["center_lng"],
                camera_heading_deg=seed["camera_heading_deg"],
                radius_m=seed["radius_m"],
                is_curated=True,
                status="pending",
                progress_stage="queued",
                eras=seed.get("eras", settings.default_eras),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(tour)
            session.commit()
            print(f"Created {tour.id} for {tour.name}")
        await run_tour_pipeline(
            tour_id=tour.id,
            lat=seed["center_lat"],
            lng=seed["center_lng"],
            heading_deg=seed["camera_heading_deg"],
            radius_m=seed["radius_m"],
        )
        print(f"Finished {tour.id}")


def _complete_cached_tour(session: Session, seed: dict) -> Tour | None:
    eras = seed.get("eras", get_settings().default_eras)
    tours = session.exec(
        select(Tour)
        .where(Tour.slug == seed["slug"], Tour.is_curated == True)  # noqa: E712
        .order_by(Tour.created_at.desc())
    ).all()
    for tour in tours:
        if tour.eras == eras and _is_complete(session, tour):
            return tour
    return None


def _is_complete(session: Session, tour: Tour) -> bool:
    if tour.status != "ready":
        return False
    nodes = session.exec(select(Node).where(Node.tour_id == tour.id)).all()
    if not nodes:
        return False
    views = session.exec(select(View).where(View.node_id.in_([node.id for node in nodes]))).all()
    expected = len(nodes) * len(tour.eras) * 4
    existing = [view for view in views if _usable(view.image_path)]
    return expected > 0 and len(existing) >= expected


def _exists(path: str) -> bool:
    image = Path(path)
    return image.exists() if image.is_absolute() else image.exists() or (Path.cwd() / image).exists()


def _usable(path: str) -> bool:
    image = Path(path)
    if not image.is_absolute() and not image.exists():
        image = Path.cwd() / image
    if not image.exists():
        return False
    try:
        head = image.read_bytes()[:8192]
    except OSError:
        return False
    blocked = (b"Generation failed", b"RESOURCE_EXHAUSTED", b"spending cap")
    return not any(marker in head for marker in blocked)


if __name__ == "__main__":
    asyncio.run(main())
