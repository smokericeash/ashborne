import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { api } from "../services/api";
import { renderWithContexts } from "../test/render";
import { OperatorConsolePage } from "./OperatorConsolePage";

describe("OperatorConsolePage", () => {
  it("rejects unknown commands and supports history and autocomplete", async () => {
    vi.spyOn(api.agents, "list").mockResolvedValue({
      items: [],
      total: 0,
      skip: 0,
      limit: 100,
    });
    const user = userEvent.setup();
    renderWithContexts(<OperatorConsolePage />);
    const input = await screen.findByLabelText("ashborne [0] >");

    await user.type(input, "curl example.invalid{Enter}");
    expect(await screen.findByText("Unsupported command.")).toBeInTheDocument();

    await user.type(input, "help{Enter}");
    fireEvent.keyDown(input, { key: "ArrowUp" });
    expect(input).toHaveValue("help");
    await user.clear(input);
    await user.type(input, "quick-r");
    fireEvent.keyDown(input, { key: "Tab" });
    expect(input).toHaveValue("quick-recon");
  });

  it("restores selected hosts and maps an alias to one typed task per host", async () => {
    sessionStorage.setItem(
      "ashborne.selected-hosts",
      JSON.stringify([
        { id: "agent-1", name: "kali-01", hostname: "kali-01", status: "ONLINE" },
        { id: "agent-2", name: "lab-02", hostname: "lab-02", status: "ONLINE" },
      ]),
    );
    vi.spyOn(api.agents, "list").mockResolvedValue({
      items: [],
      total: 0,
      skip: 0,
      limit: 100,
    });
    const bulkCreate = vi.spyOn(api.tasks, "bulkCreate").mockResolvedValue({
      bulk_operation_id: "operation-1",
      task_type: "HOSTNAME",
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
        EXPIRED: 0,
      },
      tasks: [],
    });
    const user = userEvent.setup();
    renderWithContexts(<OperatorConsolePage />);

    await user.click(
      screen.getByRole("checkbox", { name: "Confirm authorized scope" }),
    );
    await user.type(screen.getByLabelText("ashborne [2] >"), "hostname{Enter}");

    await waitFor(() =>
      expect(bulkCreate).toHaveBeenCalledWith(
        ["agent-1", "agent-2"],
        "HOSTNAME",
        true,
      ),
    );
    expect(await screen.findByText(/HOSTNAME queued for 2 hosts/)).toBeInTheDocument();
  });
});
