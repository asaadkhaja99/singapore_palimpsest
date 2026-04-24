from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from backend.pipeline.geometry import DIRECTION_HEADINGS


def equirectangular_to_perspective(
    source_path: str | Path,
    out_path: str | Path,
    yaw_deg: float,
    pitch_deg: float = 0,
    fov_deg: float = 90,
    width: int = 1280,
    height: int = 720,
    max_source_width: int = 4096,
) -> Path:
    source_path = Path(source_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    image = Image.open(source_path).convert("RGB")
    if image.width > max_source_width:
        resized_height = int(image.height * max_source_width / image.width)
        image = image.resize((max_source_width, resized_height), Image.Resampling.LANCZOS)
    source = np.asarray(image)
    src_h, src_w = source.shape[:2]

    x = (np.arange(width) + 0.5) / width
    y = (np.arange(height) + 0.5) / height
    xx, yy = np.meshgrid(x, y)

    aspect = width / height
    tan_half = np.tan(np.deg2rad(fov_deg) / 2)
    cam_x = np.ones_like(xx)
    cam_y = (2 * xx - 1) * tan_half
    cam_z = (1 - 2 * yy) * tan_half / aspect

    norm = np.sqrt(cam_x**2 + cam_y**2 + cam_z**2)
    cam_x /= norm
    cam_y /= norm
    cam_z /= norm

    pitch = np.deg2rad(pitch_deg)
    pitched_x = cam_x * np.cos(pitch) - cam_z * np.sin(pitch)
    pitched_z = cam_x * np.sin(pitch) + cam_z * np.cos(pitch)
    cam_x = pitched_x
    cam_z = pitched_z

    yaw = np.deg2rad(yaw_deg)
    world_x = cam_x * np.cos(yaw) - cam_y * np.sin(yaw)
    world_y = cam_x * np.sin(yaw) + cam_y * np.cos(yaw)
    world_z = cam_z

    lon = np.arctan2(world_y, world_x)
    lat = np.arcsin(np.clip(world_z, -1, 1))
    src_x = ((lon / (2 * np.pi) + 0.5) % 1.0) * (src_w - 1)
    src_y = (0.5 - lat / np.pi) * (src_h - 1)

    sampled = _bilinear_sample(source, src_x, src_y)
    Image.fromarray(sampled.astype(np.uint8), "RGB").save(out_path, quality=92)
    return out_path


def _bilinear_sample(source: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    src_h, src_w = source.shape[:2]
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    x1 = (x0 + 1) % src_w
    y1 = np.clip(y0 + 1, 0, src_h - 1)
    x0 = x0 % src_w
    y0 = np.clip(y0, 0, src_h - 1)

    wx = x - x0
    wy = y - y0
    top = source[y0, x0] * (1 - wx[..., None]) + source[y0, x1] * wx[..., None]
    bottom = source[y1, x0] * (1 - wx[..., None]) + source[y1, x1] * wx[..., None]
    return top * (1 - wy[..., None]) + bottom * wy[..., None]


def create_direction_crops(
    source_path: str | Path,
    output_dir: str | Path,
    source_heading_deg: float | None,
    fov_deg: int = 90,
    width: int = 1280,
    height: int = 720,
) -> dict[str, str]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base_heading = source_heading_deg or 0
    crops: dict[str, str] = {}
    for direction, absolute_heading in DIRECTION_HEADINGS.items():
        relative_yaw = (absolute_heading - base_heading) % 360
        out_path = output_dir / f"{direction}.jpg"
        crops[direction] = str(
            equirectangular_to_perspective(
                source_path,
                out_path,
                yaw_deg=relative_yaw,
                pitch_deg=0,
                fov_deg=fov_deg,
                width=width,
                height=height,
            )
        )
    return crops
