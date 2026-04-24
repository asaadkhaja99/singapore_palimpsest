"use client";

import { apiFetch, ResolveResponse } from "@/lib/api";
import { grabTransformRequest, loadMapStyle } from "@/lib/maplibre";
import { Compass, Navigation } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

const DEFAULT_PICK = { lat: 1.2807, lng: 103.8472 };
const DEFAULT_HEADING = 25;

export function MapPicker() {
  const mapRef = useRef<HTMLDivElement | null>(null);
  const markerRef = useRef<import("maplibre-gl").Marker | null>(null);
  const [pick, setPick] = useState(DEFAULT_PICK);
  const [heading, setHeading] = useState(DEFAULT_HEADING);
  const [radius, setRadius] = useState(100);
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  useEffect(() => {
    let map: import("maplibre-gl").Map | null = null;
    let cancelled = false;
    async function init() {
      if (!mapRef.current) return;
      const maplibregl = await import("maplibre-gl");
      const style = await loadMapStyle();
      if (cancelled || !mapRef.current) return;
      map = new maplibregl.Map({
        container: mapRef.current,
        style,
        center: [DEFAULT_PICK.lng, DEFAULT_PICK.lat],
        zoom: 17,
        transformRequest: grabTransformRequest,
      });
      map.addControl(new maplibregl.NavigationControl(), "top-left");
      markerRef.current = new maplibregl.Marker({ color: "#d7a84f" })
        .setLngLat([DEFAULT_PICK.lng, DEFAULT_PICK.lat])
        .addTo(map);
      map.on("click", (event) => {
        const next = { lat: event.lngLat.lat, lng: event.lngLat.lng };
        setPick(next);
        markerRef.current?.setLngLat([next.lng, next.lat]);
      });
    }
    init();
    return () => {
      cancelled = true;
      markerRef.current?.remove();
      map?.remove();
    };
  }, []);

  async function submit() {
    setBusy(true);
    try {
      const response = await apiFetch<ResolveResponse>("/api/tours/resolve", {
        method: "POST",
        body: JSON.stringify({ ...pick, radius_m: radius, heading_deg: heading, name: "Live Singapore route" }),
      });
      router.push(`/resolving/${response.tour_id}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div className="map-frame" ref={mapRef} />
      <div className="card" style={{ display: "grid", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <span className="muted">
            {pick.lat.toFixed(5)}, {pick.lng.toFixed(5)}
          </span>
          <button className="button" onClick={submit} disabled={busy}>
            <Navigation size={18} />
            {busy ? "Starting" : "Resolve Tour"}
          </button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 160px", gap: 14, alignItems: "end" }}>
          <label style={{ display: "grid", gap: 8 }}>
            <span className="muted" style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              <Compass size={16} />
              Camera heading: {heading}°
            </span>
            <input
              aria-label="Camera heading"
              type="range"
              min={0}
              max={359}
              step={1}
              value={heading}
              onChange={(event) => setHeading(Number(event.target.value))}
              style={{ width: "100%", accentColor: "var(--accent)" }}
            />
          </label>
          <label style={{ display: "grid", gap: 8 }}>
            <span className="muted">Route length</span>
            <select
              value={radius}
              onChange={(event) => setRadius(Number(event.target.value))}
              style={{
                minHeight: 40,
                borderRadius: 8,
                border: "1px solid var(--line)",
                background: "#101216",
                color: "var(--text)",
                padding: "0 10px",
              }}
            >
              <option value={75}>75m</option>
              <option value={100}>100m</option>
              <option value={150}>150m</option>
              <option value={200}>200m</option>
            </select>
          </label>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {[
            ["N", 0],
            ["E", 90],
            ["S", 180],
            ["W", 270],
          ].map(([label, value]) => (
            <button
              className="button secondary"
              key={label}
              onClick={() => setHeading(Number(value))}
              style={{ minHeight: 34 }}
              type="button"
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
