import Link from "next/link";
import { MapPicker } from "@/components/MapPicker";

export default function PickPage() {
  return (
    <main className="page-shell">
      <div className="topbar">
        <div>
          <div className="brand">Pick a Location</div>
          <div className="muted">Click the map to choose a Singapore street-level viewpoint.</div>
        </div>
        <Link className="button secondary" href="/">
          Home
        </Link>
      </div>
      <MapPicker />
    </main>
  );
}
