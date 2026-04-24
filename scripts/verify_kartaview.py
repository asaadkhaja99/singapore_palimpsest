from __future__ import annotations

import asyncio

from backend.config import get_settings
from backend.integrations.kartaview import KartaViewProvider


async def main() -> None:
    provider = KartaViewProvider(get_settings())
    photos = await provider.nearby_photos(1.2807, 103.8472, radius_m=100, heading_deg=25)
    if not photos:
        raise SystemExit("No KartaView photos found near Telok Ayer.")
    photo = photos[0]
    details = await provider.photo_details(photo.photo_id)
    print(
        {
            "photo_id": details.photo_id,
            "sequence_id": details.sequence_id,
            "lat": details.lat,
            "lng": details.lng,
            "heading": details.heading,
            "projection": details.projection,
            "field_of_view": details.field_of_view,
            "has_imageProcUrl": bool(details.image_proc_url),
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
