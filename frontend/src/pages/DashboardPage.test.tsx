import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { tokenStore } from "../services/tokenStore";
import { renderWithContexts } from "../test/render";
import { DashboardPage } from "./DashboardPage";

const backendAgent = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  agent_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  name: "lab-sensor-01",
  hostname: "lab-sensor-01",
  username: "ashborne",
  operating_system: "Linux",
  os_version: "Debian 13",
  architecture: "x86_64",
  ip_address: "192.0.2.10",
  agent_version: "0.1.0",
  first_seen: "2026-09-10T00:00:00Z",
  last_seen: "2026-09-14T01:00:00Z",
  status: "ONLINE",
  tags: ["lab"],
  uptime_seconds: 600,
};

describe("DashboardPage", () => {
  beforeEach(() => {
    tokenStore.clear();
    tokenStore.set("test-access", "test-refresh");
  });

  it("renders metrics and activity returned with backend field names", async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/dashboard/metrics")) {
        return new Response(
          JSON.stringify({
            total_agents: 3,
            online_agents: 2,
            degraded_agents: 1,
            offline_agents: 0,
            tasks_queued: 4,
            tasks_running: 1,
            tasks_completed: 8,
            tasks_failed: 2,
            task_success_rate: 75,
            average_checkin_interval_seconds: 31.5,
            os_distribution: { Linux: 2, Windows: 1 },
            version_distribution: { "0.1.0": 3 },
            tasks_over_time: [
              { date: "2026-09-14", created: 3, success: 2, failed: 1 },
            ],
            heartbeat_activity: [{ date: "2026-09-14", count: 92 }],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.endsWith("/dashboard/activity")) {
        return new Response(
          JSON.stringify({
            agents: [backendAgent],
            tasks: [
              {
                id: "task-1",
                agent_id: backendAgent.id,
                task_type: "CPU_INFO",
                parameters: {},
                requested_by_id: "operator-1",
                created_at: "2026-09-14T00:30:00Z",
                expires_at: "2026-09-14T01:30:00Z",
                status: "SUCCESS",
                result: { task_type: "CPU_INFO", data: { logical_cores: 8 } },
              },
            ],
            audit_events: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithContexts(<DashboardPage />);

    expect(await screen.findByText("lab-sensor-01")).toBeInTheDocument();
    expect(screen.getByText("CPU_INFO")).toBeInTheDocument();
    expect(
      within(screen.getByText("Lab hosts").parentElement!).getByText("3"),
    ).toBeInTheDocument();
    expect(screen.getByText("Linux: 2 agents")).toBeInTheDocument();
    expect(screen.getByText("Windows: 1 agents")).toBeInTheDocument();
    expect(screen.getByText("0.1.0: 3 agents")).toBeInTheDocument();
    expect(screen.getByText("Avg check-in 32s")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
