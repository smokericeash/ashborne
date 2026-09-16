import { createContext, useContext } from "react";
import type { LiveEvent } from "../types";

export interface LiveContextValue {
  connected: boolean;
  lastEvent: LiveEvent | null;
  revision: number;
}

export const LiveContext = createContext<LiveContextValue>({
  connected: false,
  lastEvent: null,
  revision: 0,
});

export function useLive() {
  return useContext(LiveContext);
}
