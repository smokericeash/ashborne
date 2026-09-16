import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { LiveEvent } from "../types";
import { subscribeToEvents } from "../services/events";
import { LiveContext } from "./useLive";

export function LiveProvider({ children }: { children: ReactNode }) {
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<LiveEvent | null>(null);
  const [revision, setRevision] = useState(0);

  useEffect(
    () =>
      subscribeToEvents((event) => {
        setLastEvent(event);
        setRevision((current) => current + 1);
      }, setConnected),
    [],
  );

  const value = useMemo(
    () => ({ connected, lastEvent, revision }),
    [connected, lastEvent, revision],
  );
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}
