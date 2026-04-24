"use client";

import { apiFetch, ResolveResponse, SystemStatus } from "@/lib/api";
import Link from "next/link";
import { MapPin, Play } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function Home() {
  const router = useRouter();
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    apiFetch<SystemStatus>("/api/status").then(setStatus).catch(() => setStatus(null));
  }, []);

  async function startTelokAyer() {
    setBusy(true);
    try {
      const response = await apiFetch<ResolveResponse>("/api/tours/curated/telok-ayer-street/resolve", {
        method: "POST",
      });
      router.push(response.status === "refused" ? `/refused/${response.tour_id}` : `/resolving/${response.tour_id}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page-shell">
      <div className="topbar">
        <div>
          <div className="brand">Palimpsest</div>
          <div className="muted">Historical street view for Singapore</div>
        </div>
        <Link className="button secondary" href="/pick">
          <MapPin size={18} />
          Pick Location
        </Link>
      </div>

      <section className="grid">
        <div className="card">
          <h1 style={{ marginTop: 0 }}>Telok Ayer Street</h1>
          <p className="muted">
            Start with the hero corridor: religious landmarks, shophouses, and a dense street-level record.
          </p>
          <button className="button" onClick={startTelokAyer} disabled={busy}>
            <Play size={18} />
            {busy ? "Starting" : "Generate Tour"}
          </button>
        </div>
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Live pick</h2>
          <p className="muted">
            Click any Singapore location. If KartaView imagery or landmark evidence is weak, Palimpsest refuses the
            route instead of inventing one.
          </p>
          <Link className="button secondary" href="/pick">
            <MapPin size={18} />
            Open Picker
          </Link>
        </div>
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Pipeline Status</h2>
          {status ? (
            <>
              <p className="muted">
                {status.full_pipeline_ready
                  ? "Full pipeline is configured."
                  : `Missing: ${status.missing.join(", ")}`}
              </p>
              <div style={{ display: "grid", gap: 8 }}>
                <StatusRow label="GrabMaps" ready={status.grabmaps_configured} />
                <StatusRow label="KartaView" ready={status.kartaview_configured} />
                <StatusRow label="Gemini" ready={status.gemini_configured} />
              </div>
            </>
          ) : (
            <p className="muted">Backend status unavailable.</p>
          )}
        </div>
      </section>
    </main>
  );
}

function StatusRow({ label, ready }: { label: string; ready: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
      <span>{label}</span>
      <span style={{ color: ready ? "var(--accent)" : "var(--accent-2)" }}>{ready ? "Ready" : "Missing"}</span>
    </div>
  );
}
