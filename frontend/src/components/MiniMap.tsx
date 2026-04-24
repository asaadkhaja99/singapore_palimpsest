"use client";

import { grabTransformRequest, loadMapStyle } from "@/lib/maplibre";
import type { TourNode } from "@/lib/api";
import { useEffect, useRef } from "react";

export function MiniMap({ nodes, currentNodeId }: { nodes: TourNode[]; currentNodeId: string }) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let map: import("maplibre-gl").Map | null = null;
    let cancelled = false;
    async function init() {
      if (!ref.current || !nodes.length) return;
      const maplibregl = await import("maplibre-gl");
      const style = await loadMapStyle();
      if (cancelled || !ref.current) return;
      map = new maplibregl.Map({
        container: ref.current,
        style,
        center: [nodes[0].lng, nodes[0].lat],
        zoom: 17,
        interactive: false,
        attributionControl: false,
        transformRequest: grabTransformRequest,
      });
      map.on("load", () => {
        if (!map) return;
        map.addSource("nodes", {
          type: "geojson",
          data: {
            type: "FeatureCollection",
            features: nodes.map((node) => ({
              type: "Feature",
              geometry: { type: "Point", coordinates: [node.lng, node.lat] },
              properties: { current: node.id === currentNodeId },
            })),
          },
        });
        map.addLayer({
          id: "nodes",
          type: "circle",
          source: "nodes",
          paint: {
            "circle-radius": ["case", ["get", "current"], 7, 5],
            "circle-color": ["case", ["get", "current"], "#d7a84f", "#4fb477"],
            "circle-stroke-color": "#101216",
            "circle-stroke-width": 2,
          },
        });
      });
    }
    init();
    return () => {
      cancelled = true;
      map?.remove();
    };
  }, [nodes, currentNodeId]);

  return <div ref={ref} className="mini-map" />;
}
