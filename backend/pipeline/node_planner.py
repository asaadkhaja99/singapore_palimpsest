from __future__ import annotations

from backend.config import Settings
from backend.integrations.places import PlacesProvider
from backend.integrations.street_level import StreetLevelProvider
from backend.pipeline.geometry import project_point, sample_waypoints
from backend.pipeline.street_level_capture import StreetLevelUnavailable, capture_street_level
from backend.pipeline.types import NodePlan


async def plan_nodes(
    *,
    settings: Settings,
    places: PlacesProvider,
    street_level: StreetLevelProvider,
    lat: float,
    lng: float,
    heading_deg: float,
    radius_m: int,
    count: int | None = None,
) -> list[NodePlan]:
    count = count or settings.default_node_count
    end_lat, end_lng = project_point(lat, lng, heading_deg, radius_m)
    try:
        route = await places.walking_route(lat, lng, end_lat, end_lng)
        route_points = [(point.lat, point.lng, point.distance_from_start_m) for point in route]
    except Exception:
        route_points = [(lat, lng, 0.0), (end_lat, end_lng, float(radius_m))]
    sampled = sample_waypoints(route_points, count)

    plans: list[NodePlan] = []
    for source_index, (node_lat, node_lng) in enumerate(sampled):
        try:
            capture = await capture_street_level(
                settings=settings,
                provider=street_level,
                lat=node_lat,
                lng=node_lng,
                heading_deg=heading_deg,
                node_key=f"{node_lat:.6f}_{node_lng:.6f}_{source_index}",
            )
        except StreetLevelUnavailable:
            continue
        except Exception:
            continue
        plans.append(NodePlan(order_index=len(plans), lat=node_lat, lng=node_lng, capture=capture))
    return plans
