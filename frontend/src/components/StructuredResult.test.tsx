import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { api } from "../services/api";
import { renderWithContexts } from "../test/render";
import type { AshborneTask } from "../types";
import { StructuredResult } from "./StructuredResult";

const task: AshborneTask = {
  id: "task-1",
  agent_id: "agent-1",
  agent_name: "kali-01",
  task_type: "NETWORK_INTERFACES",
  created_at: "2026-09-20T00:00:00Z",
  completed_at: "2026-09-20T00:00:03Z",
  status: "SUCCESS",
  result: {
    data: {
      interfaces: [
        {
          name: "eth0",
          is_up: true,
          addresses: [{ family: "IPv4", address: "172.22.0.5" }],
        },
      ],
    },
  },
};

describe("StructuredResult", () => {
  it("uses an operator-friendly summary before raw JSON", async () => {
    const user = userEvent.setup();
    const listAudit = vi.spyOn(api.audit, "list").mockResolvedValue({
      items: [
        {
          id: "audit-1",
          event_type: "TASK_COMPLETED",
          timestamp: "2026-09-20T00:00:03Z",
          agent_id: "agent-1",
          agent_name: "kali-01",
          metadata: { task_id: "task-1" },
        },
      ],
      total: 1,
      skip: 0,
      limit: 100,
    });
    renderWithContexts(<StructuredResult task={task} />);

    expect(
      screen.getByRole("columnheader", { name: "Interface" }),
    ).toBeInTheDocument();
    expect(screen.getByText("eth0")).toBeInTheDocument();
    expect(screen.getByText("172.22.0.5")).toBeInTheDocument();
    expect(screen.queryByText(/"interfaces"/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Raw/ }));
    expect(screen.getByText(/"interfaces"/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Timeline/ }));
    expect(screen.getByText("Created")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Audit/ }));
    expect(await screen.findByText("TASK_COMPLETED")).toBeInTheDocument();
    expect(listAudit).toHaveBeenCalledWith({ search: "task-1", limit: 100 });
  });

  it("renders CPU usage for process results", () => {
    renderWithContexts(
      <StructuredResult
        task={{
          ...task,
          task_type: "PROCESS_INVENTORY",
          result: {
            processes: [
              {
                pid: 42,
                username: "operator",
                name: "ashborne-agent",
                cpu_percent: 12.35,
                memory_percent: 6.79,
              },
            ],
          },
        }}
      />,
    );

    expect(
      screen.getByRole("columnheader", { name: "CPU" }),
    ).toBeInTheDocument();
    expect(screen.getByText("12.35%")).toBeInTheDocument();
  });

  it("renders nested network-overview collections as tables", () => {
    renderWithContexts(
      <StructuredResult
        task={{
          ...task,
          task_type: "NETWORK_OVERVIEW",
          result: {
            interfaces: {
              interfaces: [
                {
                  name: "eth0",
                  is_up: true,
                  addresses: [{ address: "172.22.0.5" }],
                },
              ],
            },
            routes: {
              routes: [
                {
                  interface: "eth0",
                  destination: "0.0.0.0/0",
                  gateway: "172.22.0.1",
                },
              ],
            },
            listening_ports: {
              listeners: [
                {
                  transport: "tcp",
                  local_address: "0.0.0.0",
                  local_port: 8000,
                  process_name: "python",
                },
              ],
            },
            connections: { connections: [] },
          },
        }}
      />,
    );

    expect(screen.getByText("Interfaces")).toBeInTheDocument();
    expect(screen.getByText("Routes")).toBeInTheDocument();
    expect(screen.getByText("Listening ports")).toBeInTheDocument();
    expect(screen.getByText("172.22.0.5")).toBeInTheDocument();
    expect(screen.getByText("172.22.0.1")).toBeInTheDocument();
  });
});
