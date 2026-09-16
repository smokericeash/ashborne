import type { LiveEvent } from "../types";
import { API_ROOT, invalidateSession, refreshAccessToken } from "./api";
import { tokenStore } from "./tokenStore";

type EventHandler = (event: LiveEvent) => void;
type StateHandler = (connected: boolean) => void;

export function parseEventBlock(block: string): LiveEvent | null {
  let eventType = "message";
  const data: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) eventType = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (!data.length) return null;
  try {
    const parsed = JSON.parse(data.join("\n"));
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      const envelope = parsed as Record<string, unknown>;
      const type =
        typeof envelope.type === "string"
          ? envelope.type
          : typeof envelope.event === "string"
            ? envelope.event
            : eventType;
      return {
        type,
        ...(typeof envelope.timestamp === "string"
          ? { timestamp: envelope.timestamp }
          : {}),
        data: "data" in envelope ? envelope.data : envelope,
      };
    }
    return { type: eventType, data: parsed };
  } catch {
    return { type: eventType, data: data.join("\n") };
  }
}

export function subscribeToEvents(
  onEvent: EventHandler,
  onState?: StateHandler,
) {
  const controller = new AbortController();
  let stopped = false;
  let retryDelay = 1000;

  const connect = async () => {
    while (!stopped) {
      try {
        const token = tokenStore.getAccess();
        const response = await fetch(`${API_ROOT}/events/stream`, {
          headers: {
            Accept: "text/event-stream",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          credentials: "same-origin",
          signal: controller.signal,
        });
        if (response.status === 401) {
          const refreshed = await refreshAccessToken();
          if (refreshed) {
            retryDelay = 1000;
            continue;
          }
          onState?.(false);
          invalidateSession();
          return;
        }
        if (!response.ok || !response.body)
          throw new Error(`Event stream unavailable (${response.status})`);
        onState?.(true);
        retryDelay = 1000;
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!stopped) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split(/\r?\n\r?\n/);
          buffer = blocks.pop() ?? "";
          blocks.forEach((block) => {
            const event = parseEventBlock(block);
            if (event && event.type !== "keepalive") onEvent(event);
          });
        }
      } catch (error) {
        if (
          stopped ||
          (error instanceof DOMException && error.name === "AbortError")
        )
          return;
      }
      if (stopped) return;
      onState?.(false);
      await new Promise((resolve) => setTimeout(resolve, retryDelay));
      retryDelay = Math.min(retryDelay * 2, 30000);
    }
  };

  void connect();
  return () => {
    stopped = true;
    controller.abort();
    onState?.(false);
  };
}
