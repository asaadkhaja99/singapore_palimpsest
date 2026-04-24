"use client";

import { imgUrl, TourPayload, Direction, FrameLandmark } from "@/lib/api";
import { useStreetViewStore } from "@/store/streetView";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Info, MapPinned, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { MiniMap } from "./MiniMap";
import { POICard } from "./POICard";
import { TimelineSlider } from "./TimelineSlider";

const DIRECTIONS: Direction[] = ["N", "E", "S", "W"];
type PanelMode = "history" | "sources" | "generation";

export function StreetView({ tour }: { tour: TourPayload }) {
  const { currentNodeId, direction, era, setCurrentNodeId, setDirection, setEra } = useStreetViewStore();
  const [activePoiId, setActivePoiId] = useState<string | null>(null);
  const [showLessonPanel, setShowLessonPanel] = useState(false);
  const [panelMode, setPanelMode] = useState<PanelMode>("history");
  const currentNode = useMemo(
    () => tour.nodes.find((node) => node.id === currentNodeId) ?? tour.nodes[0],
    [currentNodeId, tour.nodes],
  );
  const currentEra = era ?? tour.eras[0];
  const activeViewContext = currentNode?.view_contexts?.[String(currentEra)]?.[direction] ?? null;
  const landmarkById = useMemo(() => {
    return new Map((currentNode?.landmarks ?? []).map((landmark) => [landmark.id, landmark]));
  }, [currentNode]);
  const activeLandmarks = useMemo(() => {
    const grounded = activeViewContext?.grounded_landmark_ids ?? [];
    const matched = grounded
      .map((id) => landmarkById.get(id))
      .filter((landmark): landmark is FrameLandmark => Boolean(landmark));
    return matched.length ? uniqueLandmarks(matched).slice(0, 6) : uniqueLandmarks(currentNode?.landmarks ?? []).slice(0, 6);
  }, [activeViewContext, currentNode, landmarkById]);
  const visiblePois = useMemo(() => {
    return tour.pois.filter((poi) => poi.visible_from_node_ids.includes(currentNode?.id ?? ""));
  }, [currentNode, tour.pois]);
  const lessonSources = useMemo(() => {
    const sources = activeLandmarks.flatMap((landmark) => landmark.era_facts?.[String(currentEra)]?.sources ?? []);
    return Array.from(new Set(sources)).slice(0, 5);
  }, [activeLandmarks, currentEra]);
  const photoAnchors = useMemo(() => {
    const current = tour.photo_anchors.filter((anchor) => anchor.era === currentEra);
    const rest = tour.photo_anchors.filter((anchor) => anchor.era !== currentEra);
    return [...current, ...rest];
  }, [currentEra, tour.photo_anchors]);

  useEffect(() => {
    if (!currentNodeId && tour.nodes[0]) setCurrentNodeId(tour.nodes[0].id);
    if (!era && tour.eras[0]) setEra(tour.eras[0]);
  }, [currentNodeId, era, setCurrentNodeId, setEra, tour.nodes, tour.eras]);

  if (!currentNode) {
    return <div className="status-page">No nodes are available for this tour.</div>;
  }

  const image = currentNode.views[String(currentEra)]?.[direction];
  const activePoi = tour.pois.find((poi) => poi.id === activePoiId) ?? null;

  if (!image) {
    return (
      <main className="status-page">
        <div className="status-box card">
          <div className="brand">{tour.name}</div>
          <p>No generated image is available for {currentEra} {direction}. Return to the picker and start a new route.</p>
        </div>
      </main>
    );
  }

  function rotate(delta: -1 | 1) {
    const index = DIRECTIONS.indexOf(direction);
    setDirection(DIRECTIONS[(index + delta + DIRECTIONS.length) % DIRECTIONS.length]);
  }

  function move(kind: "forward" | "backward") {
    const next = currentNode.neighbors[kind];
    if (next) setCurrentNodeId(next);
  }

  return (
    <main className="street-view">
      <AnimatePresence mode="wait">
        <motion.img
          key={`${currentNode.id}-${direction}-${currentEra}-${image}`}
          src={imgUrl(image)}
          alt={`${tour.name} ${currentEra} ${direction}`}
          className="street-view-image"
          initial={false}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
        />
      </AnimatePresence>

      <button className="viewer-control" style={{ left: 18, top: "50%" }} onClick={() => rotate(-1)} aria-label="Turn left">
        <ArrowLeft />
      </button>
      <button className="viewer-control" style={{ right: 18, top: "50%" }} onClick={() => rotate(1)} aria-label="Turn right">
        <ArrowRight />
      </button>
      <button
        className="viewer-control"
        style={{ left: "50%", top: 18 }}
        onClick={() => move("forward")}
        disabled={!currentNode.neighbors.forward}
        aria-label="Move forward"
      >
        <ArrowUp />
      </button>
      <button
        className="viewer-control"
        style={{ left: "50%", bottom: 170 }}
        onClick={() => move("backward")}
        disabled={!currentNode.neighbors.backward}
        aria-label="Move backward"
      >
        <ArrowDown />
      </button>

      <MiniMap nodes={tour.nodes} currentNodeId={currentNode.id} />

      <button
        className="context-toggle"
        onClick={() => setShowLessonPanel((value) => !value)}
        aria-label="Toggle lesson panel"
      >
        <Info size={16} />
        Lesson
      </button>

      {showLessonPanel ? (
        <aside className="glass-panel context-panel">
          <div className="context-heading">
            <div>
              <div className="context-eyebrow">Explore this view</div>
              <h2>{panelTitle(panelMode)}</h2>
            </div>
            <button className="context-close" onClick={() => setShowLessonPanel(false)} aria-label="Close lesson panel">
              <X size={16} />
            </button>
          </div>

          <div className="context-tabs" aria-label="Context panel mode">
            <button className={panelMode === "history" ? "active" : ""} onClick={() => setPanelMode("history")}>
              History
            </button>
            <button className={panelMode === "sources" ? "active" : ""} onClick={() => setPanelMode("sources")}>
              Sources
            </button>
            <button className={panelMode === "generation" ? "active" : ""} onClick={() => setPanelMode("generation")}>
              Generation
            </button>
          </div>

          <div className="context-source">
            <MapPinned size={16} />
            <div>
              <strong>Node {currentNode.order_index + 1}</strong>
              <span>
                {currentNode.lat.toFixed(5)}, {currentNode.lng.toFixed(5)}
              </span>
            </div>
          </div>

          {panelMode === "history" ? (
            <>
              <p className="lesson-intro">
                This {currentEra} view is anchored to nearby GrabMaps places around this exact node, then rendered
                with historical facts and source constraints for the selected era.
              </p>

              <div className="context-section-title">What to notice</div>
              <div className="context-landmarks">
                {activeLandmarks.length ? (
                  activeLandmarks.map((landmark) => {
                    const lesson = landmark.era_facts?.[String(currentEra)];
                    return (
                      <div className="context-landmark lesson-card" key={landmark.id}>
                        <div className="context-landmark-title">{landmark.name}</div>
                        <div className="context-landmark-address">{landmark.address ?? landmark.street ?? "GrabMaps place result"}</div>
                        <div className="context-meta">
                          <span>{sourceLabel(landmark.source)}</span>
                          <span>{Math.round(landmark.estimated_distance_m)}m away</span>
                          <span>{lesson?.overall_confidence ?? landmark.identification_confidence}</span>
                        </div>
                        {lesson?.highlights?.length ? (
                          <ul className="lesson-highlights">
                            {lesson.highlights.slice(0, 3).map((item) => (
                              <li key={item}>{item}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="context-empty">This landmark is grounded by GrabMaps; detailed historical notes are limited for this era.</p>
                        )}
                      </div>
                    );
                  })
                ) : (
                  <div className="context-empty">No grounded place context is attached to this view.</div>
                )}
              </div>

              {visiblePois.length ? (
                <>
                  <div className="context-section-title">Area stories</div>
                  <div className="lesson-pois">
                    {visiblePois.slice(0, 4).map((poi) => (
                      <button className="lesson-poi" key={poi.id} onClick={() => setActivePoiId(poi.id)}>
                        <strong>{poi.name}</strong>
                        <span>{poi.historical_context}</span>
                      </button>
                    ))}
                  </div>
                </>
              ) : null}

              {lessonSources.length ? (
                <>
                  <div className="context-section-title">Sources</div>
                  <div className="lesson-sources">
                    {lessonSources.map((source) => (
                      <a href={source} key={source} target="_blank" rel="noreferrer">
                        {sourceLabelForUrl(source)}
                      </a>
                    ))}
                  </div>
                </>
              ) : null}
            </>
          ) : panelMode === "sources" ? (
            <>
              <p className="lesson-intro">
                Timeline stops are chosen to match dated or closely dated historical photo references where possible.
              </p>
              {photoAnchors.length ? (
                <>
                  <div className="context-section-title">Photo-backed timeline</div>
                  <div className="photo-anchor-list">
                    {photoAnchors.map((anchor) => (
                      <div className={anchor.era === currentEra ? "photo-anchor active" : "photo-anchor"} key={`${anchor.era}-${anchor.label}`}>
                        <strong>{anchor.era}</strong>
                        <span>{anchor.label}</span>
                        {anchor.credit ? <em>{anchor.credit}</em> : null}
                      </div>
                    ))}
                  </div>
                </>
              ) : null}
              {lessonSources.length ? (
                <>
                  <div className="context-section-title">Historical source links</div>
                  <div className="lesson-sources">
                    {lessonSources.map((source) => (
                      <a href={source} key={source} target="_blank" rel="noreferrer">
                        {sourceLabelForUrl(source)}
                      </a>
                    ))}
                  </div>
                </>
              ) : (
                <div className="context-empty">No source links are attached to the current view.</div>
              )}
            </>
          ) : (
            <>
              <div className="context-kv">
                <span>Reference</span>
                <strong>{currentNode.source_provider ?? "street-level"} / {currentNode.source_photo_id ?? "source image"}</strong>
                <span>View</span>
                <strong>
                  {currentEra} {direction} · {activeViewContext?.model_used ?? "reference"}
                </strong>
              </div>

              <div className="context-section-title">Hyperlocal places used in prompt</div>
              <div className="context-landmarks">
                {activeLandmarks.length ? (
                  activeLandmarks.map((landmark) => (
                    <div className="context-landmark" key={landmark.id}>
                      <div className="context-landmark-title">{landmark.name}</div>
                      <div className="context-landmark-address">{landmark.address ?? landmark.street ?? "GrabMaps place result"}</div>
                      <div className="context-meta">
                        <span>{sourceLabel(landmark.source)}</span>
                        <span>{Math.round(landmark.estimated_distance_m)}m</span>
                        <span>{Math.round(landmark.bearing_from_camera_deg)}°</span>
                        <span>{landmark.identification_confidence}</span>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="context-empty">No grounded place context is attached to this view.</div>
                )}
              </div>

              <details className="prompt-details">
                <summary>Prompt excerpt</summary>
                <pre>{activeViewContext?.prompt_excerpt ?? "This view is using the current-day street-level reference."}</pre>
              </details>
            </>
          )}
        </aside>
      ) : null}

      <div className="bottom-panel">
        {activePoi ? <POICard poi={activePoi} onClose={() => setActivePoiId(null)} /> : null}
        <div className="glass-panel poi-row">
          {visiblePois
            .map((poi) => (
              <button className="poi-pill" key={poi.id} onClick={() => setActivePoiId(poi.id)}>
                {poi.name}
              </button>
            ))}
        </div>
        <TimelineSlider eras={tour.eras} currentEra={currentEra} onChange={setEra} />
        <div className="muted" style={{ fontSize: 12 }}>
          {tour.imagery_attribution} {tour.generated_image_notice}
        </div>
      </div>
    </main>
  );
}

function sourceLabel(source: string): string {
  if (source === "vision+places") return "Gemini vision + GrabMaps";
  if (source === "places_only") return "GrabMaps nearby POI";
  if (source === "vision_only") return "Gemini vision";
  return source;
}

function uniqueLandmarks(landmarks: FrameLandmark[]): FrameLandmark[] {
  const seen = new Set<string>();
  const unique: FrameLandmark[] = [];
  for (const landmark of landmarks) {
    const key = landmark.place_id ?? `${landmark.name}:${landmark.address ?? ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(landmark);
  }
  return unique;
}

function sourceLabelForUrl(source: string): string {
  try {
    const url = new URL(source);
    return url.hostname.replace(/^www\./, "");
  } catch {
    return source;
  }
}

function panelTitle(mode: PanelMode): string {
  if (mode === "history") return "Historical lesson";
  if (mode === "sources") return "Sources and photo anchors";
  return "Generation inputs";
}
