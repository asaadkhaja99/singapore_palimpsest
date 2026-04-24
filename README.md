# Palimpsest

Hackathon MVP for a navigable, AI-generated historical street view of Singapore.

## Architecture

- Backend: FastAPI, SQLModel, SQLite, direct GrabMaps, KartaView/OpenStreetCam, Gemini.
- Frontend: Next.js App Router, MapLibre, TanStack Query, Zustand, Framer Motion.
- Street-level reference imagery: KartaView/OpenStreetCam spherical photos projected into `N/E/S/W` 16:9 crops.
- Places and routing: GrabMaps direct HTTP APIs.

## Environment

Copy `.env.example` to `.env` and fill:

```bash
GRABMAPS_API_KEY=...
GEMINI_API_KEY=...
NEXT_PUBLIC_GRABMAPS_API_KEY=...
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

`GEMINI_API_KEY` is required for grounding, research, and historical image generation. Without it, the backend still starts, but live tours will usually refuse because no visible structures can be grounded.

## Backend

```bash
uv sync
uv run uvicorn backend.main:app --reload
```

Useful checks:

```bash
uv run python -m scripts.verify_kartaview
uv run python -m scripts.verify_projection
uv run python -m evals.grounding_eval
uv run python scripts/prerender_curated.py
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## API

- `POST /api/tours/resolve`
- `GET /api/tours/{id}`
- `GET /api/tours/curated`
- `GET /api/places/search?q=...`
- `GET /api/places/nearby?lat=...&lng=...`

## Imagery Policy

Street-level reference imagery is from KartaView/OpenStreetCam contributors and should be displayed with attribution:

> Street-level reference imagery from KartaView/OpenStreetCam contributors, licensed under CC BY-SA 4.0. Cropped/projected for Palimpsest.

Generated historical scenes use that reference imagery and cited historical sources.
