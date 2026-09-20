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

export const LiveConnectionContext = createContext(false);
export const AgentsRevisionContext = createContext(0);
export const TasksRevisionContext = createContext(0);
export const AuditRevisionContext = createContext(0);
export const DashboardRevisionContext = createContext(0);

export function useLive() {
  return useContext(LiveContext);
}

export function useLiveConnection() {
  return useContext(LiveConnectionContext);
}

export function useAgentsRevision() {
  return useContext(AgentsRevisionContext);
}

export function useTasksRevision() {
  return useContext(TasksRevisionContext);
}

export function useAuditRevision() {
  return useContext(AuditRevisionContext);
}

export function useDashboardRevision() {
  return useContext(DashboardRevisionContext);
}
