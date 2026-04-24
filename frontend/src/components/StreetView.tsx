"use client";

import { imgUrl, TourPayload, Direction } from "@/lib/api";
import { useStreetViewStore } from "@/store/streetView";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { MiniMap } from "./MiniMap";
import { POICard } from "./POICard";
import { TimelineSlider } from "./TimelineSlider";

const DIRECTIONS: Direction[] = ["N", "E", "S", "W"];

export function StreetView({ tour }: { tour: TourPayload }) {
  const { currentNodeId, direction, era, setCurrentNodeId, setDirection, setEra } = useStreetViewStore();
  const [activePoiId, setActivePoiId] = useState<string | null>(null);
  const currentNode = useMemo(
    () => tour.nodes.find((node) => node.id === currentNodeId) ?? tour.nodes[0],
    [currentNodeId, tour.nodes],
  );
  const currentEra = era ?? tour.eras[0];

  useEffect(() => {
    if (!currentNodeId && tour.nodes[0]) setCurrentNodeId(tour.nodes[0].id);
    if (!era && tour.eras[0]) setEra(tour.eras[0]);
  }, [currentNodeId, era, setCurrentNodeId, setEra, tour.nodes, tour.eras]);

  if (!currentNode) {
    return <div className="status-page">No nodes are available for this tour.</div>;
  }

  const image = currentNode.views[String(currentEra)]?.[direction] ?? currentNode.reference_crops[direction];
  const activePoi = tour.pois.find((poi) => poi.id === activePoiId) ?? null;

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
          initial={{ opacity: 0 }}
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

      <div className="bottom-panel">
        {activePoi ? <POICard poi={activePoi} onClose={() => setActivePoiId(null)} /> : null}
        <div className="glass-panel poi-row">
          {tour.pois
            .filter((poi) => poi.visible_from_node_ids.includes(currentNode.id))
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
