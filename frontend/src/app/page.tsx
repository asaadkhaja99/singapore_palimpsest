"use client";

import { apiFetch, ResolveResponse } from "@/lib/api";
import { ArrowRight, MapPin } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

const DEMO_ROUTE = {
  id: "telok-ayer-street",
  name: "Telok Ayer Street",
  lat: 1.2807,
  lng: 103.8472,
  radius_m: 100,
  heading_deg: 25,
  description: "Strongest grounded-history corridor: temple, mosque, dargah, church, and shophouses.",
};

export default function Home() {
  const router = useRouter();
  const [startingDemo, setStartingDemo] = useState(false);

  async function startDemoRoute() {
    if (startingDemo) {
      return;
    }
    setStartingDemo(true);
    try {
      const response = await apiFetch<ResolveResponse>("/api/tours/resolve", {
        method: "POST",
        body: JSON.stringify({
          lat: DEMO_ROUTE.lat,
          lng: DEMO_ROUTE.lng,
          radius_m: DEMO_ROUTE.radius_m,
          heading_deg: DEMO_ROUTE.heading_deg,
          name: DEMO_ROUTE.name,
        }),
      });
      if (response.status === "ready") {
        router.push(`/tour/${response.tour_id}`);
      } else {
        router.push(response.status === "refused" ? `/refused/${response.tour_id}` : `/resolving/${response.tour_id}`);
      }
    } finally {
      setStartingDemo(false);
    }
  }

  return (
    <main className="page-shell landing-shell">
      <nav className="topbar">
        <div>
          <div className="brand">Palimpsest</div>
          <div className="muted">Historical street view for Singapore</div>
        </div>
        <Link className="button secondary" href="/pick">
          <MapPin size={18} />
          Pick Location
        </Link>
      </nav>

      <section className="live-hero">
        <div className="live-copy">
          <div className="context-eyebrow">Live tour</div>
          <h1>Choose a Singapore street and generate its historical view.</h1>
          <p>
            Palimpsest uses GrabMaps place context, street-level imagery, and source-backed research to build a
            navigable timeline from the viewpoint you pick.
          </p>
          <div className="live-actions">
            <Link className="button primary-action" href="/pick">
              <MapPin size={19} />
              Start Live Tour
              <ArrowRight size={18} />
            </Link>
            <button className="button primary-action secondary" onClick={startDemoRoute} disabled={startingDemo}>
              Demo Tour
              <ArrowRight size={18} />
            </button>
          </div>
        </div>
      </section>

      <section className="demo-section" aria-label="Demo route">
        <div className="demo-route-summary">
          <span className="context-eyebrow">Demo route</span>
          <strong>Telok Ayer Street</strong>
          <span>{DEMO_ROUTE.description}</span>
        </div>
      </section>
    </main>
  );
}
