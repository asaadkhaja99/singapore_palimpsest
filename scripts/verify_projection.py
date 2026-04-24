from __future__ import annotations

import asyncio

from PIL import Image

from backend.config import get_settings
from backend.integrations.kartaview import KartaViewProvider
from backend.pipeline.projection import create_direction_crops


async def main() -> None:
    settings = get_settings()
    provider = KartaViewProvider(settings)
    photos = await provider.nearby_photos(1.2807, 103.8472, radius_m=100, heading_deg=25)
    if not photos:
        raise SystemExit("No KartaView photos found near Telok Ayer.")
    details = await provider.photo_details(photos[0].photo_id)
    source = await provider.download_source_image(details)
    crops = create_direction_crops(
        source,
        settings.palimpsest_img_dir / "verify_projection" / details.photo_id,
        source_heading_deg=details.heading,
    )
    for direction, path in crops.items():
        with Image.open(path) as image:
            print(direction, path, image.size)


if __name__ == "__main__":
    asyncio.run(main())
