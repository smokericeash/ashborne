import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { api } from "../services/api";
import { renderWithContexts } from "../test/render";
import type { Agent } from "../types";
import { AgentsPage } from "./AgentsPage";

const zulu: Agent = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  agent_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  uuid: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  name: "Zulu sensor",
  hostname: "zulu-host",
  username: "svc-ashborne",
  operating_system: "Linux",
  os_version: "Debian 13",
  architecture: "x86_64",
  ip_address: "192.0.2.20",
  agent_version: "0.1.0",
  first_seen: "2026-09-10T00:00:00Z",
  last_seen: "2026-09-14T01:00:00Z",
  status: "ONLINE",
  tags: ["production", "linux", "pci"],
};

const alpha: Agent = {
  ...zulu,
  id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  agent_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  uuid: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  name: "Alpha sensor",
  hostname: "alpha-host",
  ip_address: "192.0.2.21",
  status: "DEGRADED",
  tags: ["staging"],
};

describe("AgentsPage", () => {
  it("uses server ordering and sends search, status, tag, and sort controls to the API", async () => {
    const list = vi
      .spyOn(api.agents, "list")
      .mockImplementation(async (params) => ({
        items: params.sort_by === "name" ? [alpha, zulu] : [zulu, alpha],
        total: 2,
        skip: params.skip ?? 0,
        limit: params.limit ?? 20,
      }));
    const user = userEvent.setup();
    renderWithContexts(<AgentsPage />);

    expect(await screen.findByText("Zulu sensor")).toBeInTheDocument();
    const body = screen
      .getByRole("table", { name: "ASHBORNE lab hosts" })
      .querySelector("tbody")!;
    let rows = within(body).getAllByRole("row");
    expect(rows[0]).toHaveTextContent("Zulu sensor");
    expect(rows[1]).toHaveTextContent("Alpha sensor");
    expect(screen.getByText("production")).toBeInTheDocument();
    expect(screen.getByText("linux")).toBeInTheDocument();
    expect(screen.getByText("pci")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Search lab hosts"), "edge{Enter}");
    await waitFor(() =>
      expect(list).toHaveBeenCalledWith(
        expect.objectContaining({ search: "edge", skip: 0 }),
      ),
    );

    await user.selectOptions(screen.getByLabelText("Agent status"), "DEGRADED");
    await user.type(screen.getByLabelText("Filter by tag"), "staging");
    await waitFor(() =>
      expect(list).toHaveBeenCalledWith(
        expect.objectContaining({
          search: "edge",
          status: "DEGRADED",
          tag: "staging",
        }),
      ),
    );

    await user.click(
      screen.getByRole("button", { name: "Sort by Enrollment" }),
    );
    await waitFor(() =>
      expect(list).toHaveBeenCalledWith(
        expect.objectContaining({ sort_by: "name", sort_order: "asc" }),
      ),
    );
    await waitFor(() => {
      rows = within(body).getAllByRole("row");
      expect(rows[0]).toHaveTextContent("Alpha sensor");
      expect(rows[1]).toHaveTextContent("Zulu sensor");
    });
  });

  it("selects hosts in bulk, keeps one target per agent, and clears the selection", async () => {
    vi.spyOn(api.agents, "list").mockResolvedValue({
      items: [zulu, alpha],
      total: 2,
      skip: 0,
      limit: 25,
    });
    const bulkCreate = vi.spyOn(api.tasks, "bulkCreate").mockResolvedValue({
      bulk_operation_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
      task_type: "QUICK_RECON",
      parameters: {},
      created_at: "2026-09-20T00:00:00Z",
      target_count: 2,
      status_counts: {
        QUEUED: 2,
        DISPATCHED: 0,
        RUNNING: 0,
        SUCCESS: 0,
        FAILED: 0,
        CANCELLED: 0,
        TIMED_OUT: 0,
        EXPIRED: 0,
      },
      tasks: [],
    });
    const user = userEvent.setup();
    renderWithContexts(<AgentsPage />);

    await screen.findByText("Zulu sensor");
    await user.click(
      screen.getByRole("checkbox", { name: "Select all visible lab hosts" }),
    );
    expect(screen.getByText("2 hosts selected")).toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", { name: "Select Zulu sensor" }),
    ).toBeChecked();
    expect(
      screen.getByRole("checkbox", { name: "Select Alpha sensor" }),
    ).toBeChecked();

    await user.click(screen.getByRole("button", { name: /run task/i }));
    await user.click(screen.getByRole("button", { name: "Review 2 targets" }));
    await user.click(screen.getByRole("button", { name: "Run 2 tasks" }));

    await waitFor(() =>
      expect(bulkCreate).toHaveBeenCalledWith(
        [zulu.id, alpha.id],
        "QUICK_RECON",
        true,
        {},
      ),
    );

    await user.click(
      screen.getByRole("button", { name: "Deselect all hosts" }),
    );
    expect(screen.queryByText("2 hosts selected")).not.toBeInTheDocument();
  });

  it("refreshes persisted selection metadata from the live host page", async () => {
    sessionStorage.setItem(
      "ashborne.selected-hosts",
      JSON.stringify([
        {
          id: zulu.id,
          name: zulu.name,
          hostname: zulu.hostname,
          status: "OFFLINE",
        },
      ]),
    );
    vi.spyOn(api.agents, "list").mockResolvedValue({
      items: [zulu],
      total: 1,
      skip: 0,
      limit: 25,
    });

    renderWithContexts(<AgentsPage />);
    await screen.findByText("Zulu sensor");

    await waitFor(() => {
      const persisted = JSON.parse(
        sessionStorage.getItem("ashborne.selected-hosts") ?? "[]",
      );
      expect(persisted).toEqual([
        {
          id: zulu.id,
          name: zulu.name,
          hostname: zulu.hostname,
          status: "ONLINE",
        },
      ]);
    });
  });
});
