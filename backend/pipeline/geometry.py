from __future__ import annotations

import math
import re


DIRECTION_HEADINGS = {"N": 0.0, "E": 90.0, "S": 180.0, "W": 270.0}


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6_378_137.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def angular_delta_deg(a: float | None, b: float | None) -> float:
    if a is None or b is None:
        return 180.0
    return abs((a - b + 180) % 360 - 180)


def bearing_between_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    lam1 = math.radians(lng1)
    lam2 = math.radians(lng2)
    y = math.sin(lam2 - lam1) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(lam2 - lam1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def signed_bearing_offset_deg(bearing_deg: float, camera_heading_deg: float) -> float:
    return (bearing_deg - camera_heading_deg + 540) % 360 - 180


def project_point(lat_deg: float, lng_deg: float, bearing_deg: float, distance_m: float) -> tuple[float, float]:
    radius = 6_378_137.0
    lat_1 = math.radians(lat_deg)
    lng_1 = math.radians(lng_deg)
    bearing = math.radians(bearing_deg)
    ad = distance_m / radius
    lat_2 = math.asin(
        math.sin(lat_1) * math.cos(ad) + math.cos(lat_1) * math.sin(ad) * math.cos(bearing)
    )
    lng_2 = lng_1 + math.atan2(
        math.sin(bearing) * math.sin(ad) * math.cos(lat_1),
        math.cos(ad) - math.sin(lat_1) * math.sin(lat_2),
    )
    return math.degrees(lat_2), math.degrees(lng_2)


def bbox_center_bearing(camera_heading_deg: float, fov_deg: float, bbox_2d: list[int]) -> float:
    # Gemini bbox format is [y0, x0, y1, x1], normalized 0-1000.
    x_center_norm = ((bbox_2d[1] + bbox_2d[3]) / 2) / 1000
    bearing_offset = (x_center_norm - 0.5) * fov_deg
    return (camera_heading_deg + bearing_offset) % 360


def frame_distance_m(frame_position: str) -> float:
    return {"foreground": 10.0, "middleground": 30.0, "background": 80.0}.get(frame_position, 30.0)


GENERIC_WORDS = {
    "building",
    "shop",
    "shops",
    "shophouse",
    "shophouses",
    "tower",
    "office",
    "road",
    "street",
    "mosque",
    "temple",
    "church",
    "structure",
    "facade",
    "unnamed",
}


def is_named(label: str) -> bool:
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", label)
    proper = [word for word in words if word[:1].isupper() and word.lower() not in GENERIC_WORDS]
    return len(proper) >= 1 and not label.lower().startswith("unnamed")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "tour"


def sample_waypoints(points: list[tuple[float, float, float]], count: int) -> list[tuple[float, float]]:
    if not points:
        return []
    if len(points) == 1 or count <= 1:
        return [(points[0][0], points[0][1])]
    total_distance = points[-1][2]
    if total_distance <= 0:
        return [(lat, lng) for lat, lng, _ in points[:count]]
    targets = [total_distance * idx / (count - 1) for idx in range(count)]
    sampled: list[tuple[float, float]] = []
    cursor = 0
    for target in targets:
        while cursor < len(points) - 1 and points[cursor + 1][2] < target:
            cursor += 1
        if cursor == len(points) - 1:
            sampled.append((points[cursor][0], points[cursor][1]))
            continue
        lat1, lng1, d1 = points[cursor]
        lat2, lng2, d2 = points[cursor + 1]
        ratio = 0 if d2 == d1 else (target - d1) / (d2 - d1)
        sampled.append((lat1 + (lat2 - lat1) * ratio, lng1 + (lng2 - lng1) * ratio))
    return sampled
