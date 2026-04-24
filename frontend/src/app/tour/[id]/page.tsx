import { StreetView } from "@/components/StreetView";
import { apiFetch, TourPayload } from "@/lib/api";
import Link from "next/link";

export default async function TourPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const tour = await apiFetch<TourPayload>(`/api/tours/${id}`, { cache: "no-store" });

  if (tour.status !== "ready") {
    return (
      <main className="status-page">
        <div className="status-box card">
          <div className="brand">{tour.name}</div>
          <p className="muted">Status: {tour.status}</p>
          <Link className="button" href={`/resolving/${tour.id}`}>
            Return to progress
          </Link>
        </div>
      </main>
    );
  }

  return <StreetView tour={tour} />;
}
