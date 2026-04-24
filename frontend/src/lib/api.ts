export type Direction = "N" | "E" | "S" | "W";

export type TourNode = {
  id: string;
  order_index: number;
  lat: number;
  lng: number;
  neighbors: Record<string, string | null>;
  views: Record<string, Partial<Record<Direction, string>>>;
  reference_crops: Partial<Record<Direction, string>>;
  landmarks: FrameLandmark[];
  view_contexts: Record<string, Partial<Record<Direction, ViewContext>>>;
  source_photo_id?: string | null;
  source_provider?: string | null;
  source_capture_date?: string | null;
  source_lat?: number | null;
  source_lng?: number | null;
  source_heading_deg?: number | null;
};

export type FrameLandmark = {
  id: string;
  name: string;
  address?: string | null;
  address_number?: string | null;
  street?: string | null;
  lat?: number | null;
  lng?: number | null;
  frame_position: string;
  bearing_from_camera_deg: number;
  estimated_distance_m: number;
  identification_confidence: string;
  source: string;
  place_id?: string | null;
  era_facts: Record<string, LandmarkEraLesson>;
};

export type LandmarkEraLesson = {
  era: number;
  era_label: string;
  overall_confidence: string;
  existed_in_era: boolean;
  highlights: string[];
  sources: string[];
};

export type ViewContext = {
  model_used: string;
  grounded_landmark_ids: string[];
  prompt_excerpt: string;
};

export type TourPoi = {
  id: string;
  name: string;
  lat: number;
  lng: number;
  historical_context: string;
  visible_from_node_ids: string[];
};

export type TourPayload = {
  id: string;
  name: string;
  status: "pending" | "grounding" | "researching" | "generating" | "ready" | "refused" | "failed";
  refusal_reason?: string | null;
  failure_reason?: string | null;
  progress?: { stage?: string | null; current: number; total: number } | null;
  eras: number[];
  photo_anchors: PhotoAnchor[];
  nodes: TourNode[];
  pois: TourPoi[];
  imagery_attribution?: string | null;
  generated_image_notice?: string | null;
};

export type PhotoAnchor = {
  era: number;
  label: string;
  credit?: string | null;
};

export type CuratedSeed = {
  id: string;
  name: string;
  status: "seed";
  lat: number;
  lng: number;
  heading_deg: number;
  eras: number[];
  demo_role?: string | null;
  coverage_note?: string | null;
  photo_anchors?: PhotoAnchor[];
  ready_tour_id?: string | null;
};

export type CuratedReady = {
  id: string;
  slug: string;
  name: string;
  status: string;
  lat: number;
  lng: number;
  heading_deg: number;
  eras: number[];
  photo_anchors?: PhotoAnchor[];
};

export type CuratedToursResponse = {
  ready: CuratedReady[];
  seeds: CuratedSeed[];
};

export type ResolveResponse = {
  tour_id: string;
  status: string;
  poll_url?: string | null;
};

export type SystemStatus = {
  backend_ready: boolean;
  grabmaps_configured: boolean;
  gemini_configured: boolean;
  openai_configured: boolean;
  research_provider: string;
  kartaview_configured: boolean;
  full_pipeline_ready: boolean;
  missing: string[];
};

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json() as Promise<T>;
}

export function imgUrl(path: string | undefined | null): string {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  return `${API_BASE}${path}`;
}
