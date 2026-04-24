from __future__ import annotations

import logging

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import get_settings
from backend.db import init_db
from backend.routes.places import router as places_router
from backend.routes.tours import router as tours_router
from backend.schemas import SystemStatusPayload


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.palimpsest_log_level)
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ]
    )
    init_db()
    app = FastAPI(title="Palimpsest API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(tours_router)
    app.include_router(places_router)
    app.mount("/img", StaticFiles(directory=settings.palimpsest_img_dir), name="img")

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/api/status", response_model=SystemStatusPayload)
    async def status():
        missing: list[str] = []
        if not settings.grabmaps_api_key:
            missing.append("GRABMAPS_API_KEY")
        if not settings.gemini_api_key:
            missing.append("GEMINI_API_KEY")
        if settings.research_provider == "openai" and not settings.openai_api_key:
            missing.append("OPENAI_API_KEY")
        return SystemStatusPayload(
            backend_ready=True,
            grabmaps_configured=bool(settings.grabmaps_api_key),
            gemini_configured=bool(settings.gemini_api_key),
            openai_configured=bool(settings.openai_api_key),
            research_provider=settings.research_provider,
            kartaview_configured=True,
            full_pipeline_ready=not missing,
            missing=missing,
        )

    return app


app = create_app()
