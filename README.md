# Palimpsest

**A navigable, AI-generated historical street view of Singapore.**

Drop a pin anywhere on the island, pick a direction, and Palimpsest reconstructs how that street looked across historical eras — grounded in real places, real walking routes, and cited historical sources. Swipe through eras, tap a landmark, and read why it was there.

Built for the Grab hackathon. GrabMaps is the spatial backbone of the whole pipeline — without it, the historical scenes would be generic; with it, they're anchored to named, real-world Singapore.

---

## Why GrabMaps is the centrepiece

Palimpsest is fundamentally a *grounding* problem: a generative model will happily hallucinate a plausible-looking 1950s Singapore, but the result is only interesting if it's tied to the actual street you're standing on. GrabMaps is how we turn "a street in Singapore" into "**Telok Ayer Street, 80m west of Thian Hock Keng Temple**" — a specific, named, geocoded place the model can be forced to respect.

We use **three distinct GrabMaps APIs** across the backend and frontend, plus the GrabMaps basemap tiles for the UI:

| Grab capability | Where we use it | Why it matters |
|---|---|---|
| `/api/v1/maps/eta/v1/direction` (walking routes) | Tour node planning | Tours follow real walkable paths, not straight lines through buildings |
| `/api/v1/maps/place/v2/nearby` (radius search) | Landmark grounding for every frame | Every AI-generated scene has a list of real, named landmarks in view with bearing + distance |
| `/api/v1/maps/poi/v1/search` (text search) | Interactive place picker | Users can search "Kampong Glam" and jump straight to a tour start |
| GrabMaps basemap style + tiles | MapPicker, MiniMap, tour viewer | Consistent SG-accurate cartography across every map surface |

---

## How a tour gets built (pipeline)

```
User drops pin  ──►  Grab walking_route  ──►  Sample nodes along path
                                                      │
                                                      ▼
                                       KartaView spherical imagery
                                       → project to N/E/S/W crops
                                                      │
                                                      ▼
                        Grab nearby(lat,lng,r=175m)  ──►  top 6 landmarks per frame
                                       (optional) Gemini vision name-match
                                                      │
                                                      ▼
                        OpenAI Responses web search (roots.gov.sg, NLB, NAS, URA)
                        grounded on the Grab place list for the area
                                                      │
                                                      ▼
                        Gemini image generation, one view per era and direction,
                        prompt includes Grab landmark names + bearings + distances
                                                      │
                                                      ▼
                                        Tour ready, served by FastAPI
```

The key insight: **Grab's place list becomes both a visual constraint on the image generator and a research target for the historian.** The same Marina Bay Sands entry that anchors the skyline in the generated image also seeds the web search for "what was here in 1950."

---

## Grab integration, file by file

### Backend

- **`backend/integrations/places_grabmaps.py`** — `GrabMapsProvider`, the async httpx client wrapping all three Grab endpoints. Handles Bearer auth, response-shape normalisation (the API returns `place_id` vs `placeId` vs `poi_id` across endpoints), and polyline6 decoding for walking routes.
- **`backend/pipeline/node_planner.py`** — Calls `walking_route()` to turn a start point + heading + radius into a list of street-level capture nodes.
- **`backend/pipeline/spatial_grounding.py`** — Calls `nearby()` for each of the four cardinal directions at every node, ranks results by angle-to-camera and distance, keeps the top 6 landmarks per frame. These are the named anchors passed to the image generator.
- **`backend/pipeline/area_research.py`** — Feeds the grounded Grab place list into the OpenAI web-search prompt (`"Mapped present-day places from GrabMaps: …"`) so the historical research targets buildings that are *actually visible*, not a generic neighbourhood summary.
- **`backend/pipeline/prompt_synth.py`** — Composes the Gemini image prompt with `"<landmark> at <bearing>°, <distance>m"` lines drawn from the Grab inventory, forcing the generator to respect real geometry.
- **`backend/routes/places.py`** — `GET /api/places/search` and `GET /api/places/nearby` expose Grab search to the frontend picker.
- **`backend/config.py`** / **`backend/main.py`** — `GRABMAPS_API_KEY` + `GRABMAPS_BASE_URL` settings, surfaced on `/api/status` so you can tell at a glance whether Grab auth is live.

### Frontend

- **`frontend/src/lib/maplibre.ts`** — Fetches `https://maps.grab.com/api/style.json` with Bearer auth, rewrites tile URLs to the API gateway path, and exposes a `transformRequest` that attaches the auth header to every MapLibre tile fetch.
- **`frontend/src/components/MapPicker.tsx`** — Tour start picker. GrabMaps basemap + live `/api/places/search` + `/api/places/nearby` as the user moves the pin.
- **`frontend/src/components/MiniMap.tsx`** — Per-node minimap on the tour viewer, same Grab style.
- **`frontend/src/components/StreetView.tsx`** — Cites "GrabMaps nearby POI" as the source when displaying landmark provenance.

---

## Tech stack

- **Backend:** FastAPI, SQLModel, SQLite, httpx
- **Places + routing:** **GrabMaps HTTP API v1**
- **Street-level reference imagery:** KartaView / OpenStreetCam spherical photos, projected to N/E/S/W 16:9 crops
- **Vision + image generation:** Gemini 3 Pro / 3 Flash (preview)
- **Historical research:** OpenAI Responses API with web-search tool, constrained to `wikipedia.org, roots.gov.sg, nlb.gov.sg, nas.gov.sg, ura.gov.sg`
- **Frontend:** Next.js 15 (App Router), React 19, MapLibre GL, TanStack Query, Zustand, Framer Motion, Tailwind

---

## Environment

Copy `.env.example` to `.env` and fill:

```bash
# Grab — used server-side for places, routing, and grounding
GRABMAPS_API_KEY=...
GRABMAPS_BASE_URL=https://maps.grab.com

# Grab — used client-side for basemap tiles + style
NEXT_PUBLIC_GRABMAPS_API_KEY=...

# Generative models
GEMINI_API_KEY=...
OPENAI_API_KEY=...
RESEARCH_PROVIDER=openai

NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

`GEMINI_API_KEY` powers historical image generation. With `RESEARCH_PROVIDER=openai`, area and landmark research use the OpenAI Responses API web-search tool, constrained to Wikipedia plus Singapore-specific sources by `OPENAI_RESEARCH_DOMAINS`.

See `.env.example` for the full set of tunables (model ids, concurrency, and timeouts).

## Run

Backend:

```bash
uv sync
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
npm install
rm -rf .next
npm run dev -- --hostname 0.0.0.0 --port 3000
```

Open `http://localhost:3000`.

The landing page is live-first:

- **Start Live Tour** opens the map picker so you can choose any Singapore location.
- **Demo Tour** starts a fresh Telok Ayer Street run.
- The demo route shown on the page is:

> Demo route  
> Telok Ayer Street  
> Strongest grounded-history corridor: temple, mosque, dargah, church, and shophouses.

Every tour is generated from the backend pipeline.

Sanity-check Grab auth end-to-end:

```bash
curl http://localhost:8000/api/status                                          # grabmaps_configured=true
curl "http://localhost:8000/api/places/search?q=Marina+Bay&lat=1.3521&lng=103.8198"
curl "http://localhost:8000/api/places/nearby?lat=1.2809&lng=103.8500&radius_m=175"
```

## Useful scripts

```bash
uv run python -m scripts.verify_kartaview      # street-level imagery availability
uv run python -m scripts.verify_projection     # spherical → cardinal crop sanity check
```

## API

- `POST /api/tours/resolve` — kick off a tour generation from a lat/lng + heading + radius
- `GET /api/tours/{id}` — poll / fetch a tour
- `GET /api/tours/curated` — list the Telok Ayer demo seed
- `GET /api/places/search?q=...&lat=...&lng=...` — GrabMaps text search passthrough
- `GET /api/places/nearby?lat=...&lng=...&radius_m=...` — GrabMaps radius search passthrough

## Imagery policy

Street-level reference imagery is from KartaView / OpenStreetCam contributors and is displayed with attribution:

> Street-level reference imagery from KartaView / OpenStreetCam contributors, licensed under CC BY-SA 4.0. Cropped/projected for Palimpsest.

Generated historical scenes use that reference imagery, GrabMaps place context, and cited historical sources.
