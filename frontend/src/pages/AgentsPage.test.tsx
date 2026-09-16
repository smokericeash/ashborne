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
  username: "svc-kandor",
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
      .getByRole("table", { name: "KANDOR agents" })
      .querySelector("tbody")!;
    let rows = within(body).getAllByRole("row");
    expect(rows[0]).toHaveTextContent("Zulu sensor");
    expect(rows[1]).toHaveTextContent("Alpha sensor");
    expect(screen.getByText("production")).toBeInTheDocument();
    expect(screen.getByText("linux")).toBeInTheDocument();
    expect(screen.getByText("pci")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Search agents"), "edge{Enter}");
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

    await user.click(screen.getByRole("button", { name: "Sort by Agent" }));
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
});
