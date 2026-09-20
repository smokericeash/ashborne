import { createContext, useContext } from "react";
import type { LiveEvent } from "../types";

export interface LiveContextValue {
  connected: boolean;
  lastEvent: LiveEvent | null;
  revision: number;
  agentsRevision: number;
  tasksRevision: number;
  auditRevision: number;
  dashboardRevision: number;
}

export const LiveContext = createContext<LiveContextValue>({
  connected: false,
  lastEvent: null,
  revision: 0,
  agentsRevision: 0,
  tasksRevision: 0,
  auditRevision: 0,
  dashboardRevision: 0,
});

export function useLive() {
  return useContext(LiveContext);
}
