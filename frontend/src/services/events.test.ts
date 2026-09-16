import { describe, expect, it, vi } from "vitest";
import { parseEventBlock } from "./events";

describe("SSE event parsing", () => {
  it("unwraps the backend event envelope", () => {
    const event = parseEventBlock(
      'event: agent.heartbeat\ndata: {"event":"agent.heartbeat","timestamp":"2026-09-14T01:00:00Z","data":{"agent_id":"agent-1","status":"ONLINE"}}',
    );

    expect(event).toEqual({
      type: "agent.heartbeat",
      timestamp: "2026-09-14T01:00:00Z",
      data: { agent_id: "agent-1", status: "ONLINE" },
    });
  });

  it("uses the SSE event name for primitive or non-envelope data", () => {
    expect(parseEventBlock('event: notice\ndata: "ready"')).toEqual({
      type: "notice",
      data: "ready",
    });
  });

  it("returns safe text for malformed JSON and ignores blocks without data", () => {
    expect(parseEventBlock("event: notice\ndata: not-json")).toEqual({
      type: "notice",
      data: "not-json",
    });
    expect(parseEventBlock(": keepalive")).toBeNull();
  });

  it("refreshes an unauthorized stream and suppresses keepalive events", async () => {
    vi.resetModules();
    sessionStorage.setItem("kandor.refresh_token", "refresh-stream");
    const encoded = new TextEncoder().encode(
      'event: keepalive\ndata: {"event":"keepalive","data":{}}\n\n' +
        'event: task.created\ndata: {"event":"task.created","data":{"task_id":"task-1"}}\n\n',
    );
    let eventAttempts = 0;
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/auth/refresh")) {
        return new Response(
          JSON.stringify({
            access_token: "fresh-access",
            refresh_token: "fresh-refresh",
            token_type: "bearer",
            expires_in: 900,
            user: {
              id: "11111111-1111-4111-8111-111111111111",
              email: "viewer@example.local",
              display_name: "Viewer",
              role: "VIEWER",
              is_active: true,
              created_at: "2026-09-01T00:00:00Z",
              updated_at: "2026-09-01T00:00:00Z",
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      eventAttempts += 1;
      if (eventAttempts === 1) return new Response(null, { status: 401 });
      return new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(encoded);
            controller.close();
          },
        }),
        { status: 200, headers: { "Content-Type": "text/event-stream" } },
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const { subscribeToEvents } = await import("./events");
    const onEvent = vi.fn();
    let unsubscribe: () => void = () => undefined;
    onEvent.mockImplementation(() => unsubscribe());
    unsubscribe = subscribeToEvents(onEvent);

    await vi.waitFor(() => expect(onEvent).toHaveBeenCalledTimes(1));
    expect(onEvent).toHaveBeenCalledWith({
      type: "task.created",
      data: { task_id: "task-1" },
    });
    expect(eventAttempts).toBe(2);
  });
});
