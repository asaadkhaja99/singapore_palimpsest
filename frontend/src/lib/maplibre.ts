import type { StyleSpecification } from "maplibre-gl";

export async function loadMapStyle(): Promise<StyleSpecification> {
  const key = process.env.NEXT_PUBLIC_GRABMAPS_API_KEY;
  if (!key) {
    return osmFallbackStyle();
  }
  const res = await fetch("https://maps.grab.com/api/style.json", {
    headers: { Authorization: `Bearer ${key}` },
  });
  if (!res.ok) {
    return osmFallbackStyle();
  }
  return normalizeGrabStyle((await res.json()) as StyleSpecification);
}

export function grabTransformRequest(url: string) {
  const key = process.env.NEXT_PUBLIC_GRABMAPS_API_KEY;
  if (key && url === "https://maps.grab.com/api/style.json") {
    return { url, headers: { Authorization: `Bearer ${key}` } };
  }
  return { url };
}

function normalizeGrabStyle(style: StyleSpecification): StyleSpecification {
  const sources = style.sources ?? {};
  for (const source of Object.values(sources)) {
    if (!source || typeof source !== "object" || !("tiles" in source) || !Array.isArray(source.tiles)) {
      continue;
    }
    source.tiles = source.tiles.map((tileUrl) =>
      typeof tileUrl === "string"
        ? tileUrl.replace("https://maps.grab.com/maps/", "https://maps.grab.com/api/maps/")
        : tileUrl,
    );
  }
  return style;
}

function osmFallbackStyle(): StyleSpecification {
  return {
    version: 8,
    sources: {
      osm: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution: "© OpenStreetMap contributors",
      },
    },
    layers: [{ id: "osm", type: "raster", source: "osm" }],
  } as StyleSpecification;
}
