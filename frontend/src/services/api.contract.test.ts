import { describe, expect, it } from "vitest";
import {
  normalizeAgent,
  normalizeDashboardActivity,
  normalizeDashboardMetrics,
  normalizeTask,
} from "./api";

const agentBase = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  agent_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  name: "lab-sensor-01",
  hostname: "lab-sensor-01",
  username: "kandor",
  operating_system: "Linux",
  os_version: "Debian 13",
  architecture: "x86_64",
  ip_address: "192.0.2.10",
  agent_version: "0.1.0",
  first_seen: "2026-09-10T00:00:00Z",
  last_seen: "2026-09-14T01:00:00Z",
  status: "ONLINE",
  tags: ["lab", "linux"],
};

function successfulTask(
  taskType: string,
  data: Record<string, unknown>,
  minute: number,
) {
  return {
    id: `${taskType.toLowerCase()}-task`,
    agent_id: agentBase.id,
    task_type: taskType,
    parameters: {},
    requested_by_id: "operator-id",
    created_at: `2026-09-14T00:${String(minute).padStart(2, "0")}:00Z`,
    expires_at: "2026-09-14T02:00:00Z",
    completed_at: `2026-09-14T00:${String(minute).padStart(2, "0")}:30Z`,
    status: "SUCCESS",
    result: {
      task_type: taskType,
      collected_at: `2026-09-14T00:${String(minute).padStart(2, "0")}:20Z`,
      data,
    },
  };
}

describe("backend response normalization", () => {
  it("maps the exact dashboard metrics and activity response field names", () => {
    const metrics = normalizeDashboardMetrics({
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
    });

    expect(metrics.average_check_in_seconds).toBe(31.5);
    expect(metrics.agents_by_os).toEqual([
      { name: "Linux", value: 2 },
      { name: "Windows", value: 1 },
    ]);
    expect(metrics.agents_by_version).toEqual([{ name: "0.1.0", value: 3 }]);
    expect(metrics.tasks_over_time[0]).toMatchObject({
      timestamp: "2026-09-14",
      total: 3,
      success: 2,
      failed: 1,
    });
    expect(metrics.heartbeat_activity[0]).toEqual({
      date: "2026-09-14",
      timestamp: "2026-09-14",
      count: 92,
    });

    const activity = normalizeDashboardActivity({
      agents: [agentBase],
      tasks: [successfulTask("HOSTNAME", { hostname: "lab-sensor-01" }, 1)],
      audit_events: [{ id: "audit-1", event_type: "AGENT_HEARTBEAT" }],
    });
    expect(activity.latest_agents[0]).toMatchObject({
      id: agentBase.id,
      name: "lab-sensor-01",
    });
    expect(activity.recent_tasks[0]).toMatchObject({
      task_type: "HOSTNAME",
      requested_by_id: "operator-id",
      requested_by: "operator-id",
    });
    expect(activity.audit_events).toHaveLength(1);
  });

  it("keeps a missing average check-in as null instead of displaying zero seconds", () => {
    expect(
      normalizeDashboardMetrics({ average_checkin_interval_seconds: null })
        .average_check_in_seconds,
    ).toBeNull();
  });

  it("maps AgentDetail recent_heartbeats, recent_tasks, and wrapped inventory results", () => {
    const agent = normalizeAgent({
      ...agentBase,
      recent_heartbeats: [
        {
          id: "heartbeat-1",
          received_at: "2026-09-14T01:00:00Z",
          reported_at: "2026-09-14T00:59:59Z",
          uptime_seconds: 900,
          agent_version: "0.1.0",
          hostname: "lab-sensor-01",
          ip_address: "192.0.2.10",
          health: { status: "healthy" },
        },
      ],
      recent_tasks: [
        successfulTask(
          "CPU_INFO",
          { physical_cores: 4, logical_cores: 8, usage_percent: 12.5 },
          1,
        ),
        successfulTask(
          "MEMORY_USAGE",
          {
            physical: {
              total_bytes: 16_000,
              available_bytes: 6_000,
              percent: 62.5,
            },
          },
          2,
        ),
        successfulTask(
          "DISK_USAGE",
          {
            partitions: [
              {
                mountpoint: "/",
                filesystem: "ext4",
                total_bytes: 100_000,
                free_bytes: 40_000,
                percent: 60,
              },
            ],
          },
          3,
        ),
        successfulTask(
          "NETWORK_INTERFACES",
          {
            interfaces: [
              {
                name: "eth0",
                is_up: true,
                addresses: [
                  { family: "IPv4", address: "192.0.2.10" },
                  { family: "MAC", address: "00:11:22:33:44:55" },
                ],
              },
            ],
          },
          4,
        ),
        successfulTask(
          "PROCESS_INVENTORY",
          {
            processes: [{ pid: 42, name: "kandor-agent", username: "kandor" }],
          },
          5,
        ),
        successfulTask(
          "LISTENING_PORTS",
          {
            listeners: [
              {
                transport: "tcp",
                local_address: "127.0.0.1",
                local_port: 8000,
                process_name: "uvicorn",
                pid: 84,
              },
            ],
          },
          6,
        ),
        successfulTask(
          "INSTALLED_SOFTWARE",
          { software: [{ name: "kandor-agent", version: "0.1.0" }] },
          7,
        ),
      ],
    });

    expect(agent.heartbeat_history?.[0]).toMatchObject({
      id: "heartbeat-1",
      timestamp: "2026-09-14T01:00:00Z",
      uptime_seconds: 900,
    });
    expect(agent.recent_tasks?.[0]).toMatchObject({
      requested_by_id: "operator-id",
    });
    expect(agent.inventory).toMatchObject({
      cpu: { physical_cores: 4, logical_cores: 8, usage_percent: 12.5 },
      memory: {
        total_bytes: 16_000,
        available_bytes: 6_000,
        used_percent: 62.5,
      },
      disks: [{ mountpoint: "/", filesystem: "ext4", used_percent: 60 }],
      interfaces: [
        {
          name: "eth0",
          addresses: ["192.0.2.10", "00:11:22:33:44:55"],
          mac_address: "00:11:22:33:44:55",
          is_up: true,
        },
      ],
      processes: [{ pid: 42, name: "kandor-agent", username: "kandor" }],
      listening_ports: [
        {
          protocol: "TCP",
          address: "127.0.0.1",
          port: 8000,
          process: "uvicorn",
          pid: 84,
        },
      ],
      installed_software: [{ name: "kandor-agent", version: "0.1.0" }],
    });
  });

  it("normalizes requester objects and requester IDs without inventing an email", () => {
    expect(
      normalizeTask({ id: "one", requested_by_id: "user-1" }),
    ).toMatchObject({
      requested_by_id: "user-1",
      requested_by: "user-1",
      requested_by_email: null,
    });
    expect(
      normalizeTask({
        id: "two",
        requested_by: { id: "user-2", email: "op@example.local" },
      }),
    ).toMatchObject({
      requested_by_id: "user-2",
      requested_by: "user-2",
      requested_by_email: "op@example.local",
    });
  });
});
