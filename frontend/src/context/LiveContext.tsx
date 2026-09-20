import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { LiveEvent } from "../types";
import { subscribeToEvents } from "../services/events";
import {
  AgentsRevisionContext,
  AuditRevisionContext,
  DashboardRevisionContext,
  LiveConnectionContext,
  LiveContext,
  TasksRevisionContext,
} from "./useLive";

export function LiveProvider({ children }: { children: ReactNode }) {
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<LiveEvent | null>(null);
  const [revision, setRevision] = useState(0);
  const [agentsRevision, setAgentsRevision] = useState(0);
  const [tasksRevision, setTasksRevision] = useState(0);
  const [auditRevision, setAuditRevision] = useState(0);
  const [dashboardRevision, setDashboardRevision] = useState(0);

  useEffect(
    () =>
      subscribeToEvents((event) => {
        setLastEvent(event);
        setRevision((current) => current + 1);
        setAuditRevision((current) => current + 1);
        setDashboardRevision((current) => current + 1);
        if (event.type.startsWith("agent."))
          setAgentsRevision((current) => current + 1);
        if (
          event.type.startsWith("task.") ||
          event.type.startsWith("bulk_operation.")
        )
          setTasksRevision((current) => current + 1);
      }, setConnected),
    [],
  );

  const value = useMemo(
    () => ({
      connected,
      lastEvent,
      revision,
      agentsRevision,
      tasksRevision,
      auditRevision,
      dashboardRevision,
    }),
    [
      connected,
      lastEvent,
      revision,
      agentsRevision,
      tasksRevision,
      auditRevision,
      dashboardRevision,
    ],
  );
  return (
    <LiveConnectionContext.Provider value={connected}>
      <AgentsRevisionContext.Provider value={agentsRevision}>
        <TasksRevisionContext.Provider value={tasksRevision}>
          <AuditRevisionContext.Provider value={auditRevision}>
            <DashboardRevisionContext.Provider value={dashboardRevision}>
              <LiveContext.Provider value={value}>{children}</LiveContext.Provider>
            </DashboardRevisionContext.Provider>
          </AuditRevisionContext.Provider>
        </TasksRevisionContext.Provider>
      </AgentsRevisionContext.Provider>
    </LiveConnectionContext.Provider>
  );
}
