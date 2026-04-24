from __future__ import annotations

import asyncio
from datetime import datetime

from sqlmodel import Session

from backend.config import get_settings
from backend.db import engine, init_db
from backend.ids import new_id
from backend.models import Tour
from backend.pipeline.orchestrator import run_tour_pipeline
from backend.seeds.curated_tours import CURATED_TOURS


async def main() -> None:
    init_db()
    settings = get_settings()
    for seed in CURATED_TOURS:
        with Session(engine) as session:
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


if __name__ == "__main__":
    asyncio.run(main())
