import { apiFetch, TourPayload } from "@/lib/api";
import Link from "next/link";

export default async function RefusedPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const tour = await apiFetch<TourPayload>(`/api/tours/${id}`, { cache: "no-store" });
  return (
    <main className="status-page">
      <div className="status-box card">
        <div className="brand">Location Refused</div>
        <p>{tour.refusal_reason ?? "This location did not have enough grounded visual history."}</p>
        <Link className="button" href="/pick">
          Select another area
        </Link>
      </div>
    </main>
  );
}
