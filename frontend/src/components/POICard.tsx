"use client";

import type { TourPoi } from "@/lib/api";

export function POICard({ poi, onClose }: { poi: TourPoi; onClose: () => void }) {
  return (
    <div className="glass-panel" style={{ padding: 16, maxWidth: 520 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
        <strong>{poi.name}</strong>
        <button className="button secondary" onClick={onClose} style={{ minHeight: 32 }}>
          Close
        </button>
      </div>
      <p className="muted" style={{ marginBottom: 0, lineHeight: 1.5 }}>
        {poi.historical_context}
      </p>
    </div>
  );
}
