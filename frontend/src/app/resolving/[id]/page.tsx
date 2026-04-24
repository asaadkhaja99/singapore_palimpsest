"use client";

import { apiFetch, TourPayload } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";

export default function ResolvingPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const query = useQuery({
    queryKey: ["tour", params.id],
    queryFn: () => apiFetch<TourPayload>(`/api/tours/${params.id}`),
    refetchInterval: 2500,
  });
  const tour = query.data;

  useEffect(() => {
    if (tour?.status === "ready") router.push(`/tour/${tour.id}`);
    if (tour?.status === "refused") router.push(`/refused/${tour.id}`);
  }, [router, tour]);

  const progress = tour?.progress;
  const percent = progress && progress.total ? Math.round((progress.current / progress.total) * 100) : 8;

  return (
    <main className="status-page">
      <div className="status-box card">
        <div className="brand">Resolving Tour</div>
        <p className="muted">{progress?.stage ?? tour?.status ?? "Queued"}</p>
        <div style={{ height: 10, borderRadius: 999, background: "rgba(255,255,255,.12)", overflow: "hidden" }}>
          <div style={{ width: `${percent}%`, height: "100%", background: "var(--accent)" }} />
        </div>
        <p className="muted">
          {progress ? `${progress.current} / ${progress.total}` : "Waiting for backend pipeline"}
        </p>
        {tour?.status === "failed" ? (
          <>
            <p>{tour.failure_reason}</p>
            <Link className="button" href="/pick">
              Try another location
            </Link>
          </>
        ) : null}
      </div>
    </main>
  );
}
