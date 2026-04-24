import { create } from "zustand";
import type { Direction } from "@/lib/api";

type StreetViewState = {
  currentNodeId: string | null;
  direction: Direction;
  era: number | null;
  setCurrentNodeId: (id: string) => void;
  setDirection: (direction: Direction) => void;
  setEra: (era: number) => void;
};

export const useStreetViewStore = create<StreetViewState>((set) => ({
  currentNodeId: null,
  direction: "N",
  era: null,
  setCurrentNodeId: (currentNodeId) => set({ currentNodeId }),
  setDirection: (direction) => set({ direction }),
  setEra: (era) => set({ era }),
}));
