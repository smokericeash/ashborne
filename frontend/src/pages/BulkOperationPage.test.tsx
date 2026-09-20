import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { api } from "../services/api";
import { renderWithContexts } from "../test/render";
import type { BulkOperation } from "../types";
import { BulkOperationPage } from "./BulkOperationPage";

const operation: BulkOperation = {
  bulk_operation_id: "operation-1",
  task_type: "QUICK_RECON",
  parameters: {},
  created_at: "2026-09-20T00:00:00Z",
  target_count: 2,
  status_counts: {
    QUEUED: 0,
    DISPATCHED: 0,
    RUNNING: 0,
    SUCCESS: 1,
    FAILED: 1,
    CANCELLED: 0,
    EXPIRED: 0,
  },
  tasks: [
    {
      id: "task-good",
      agent_id: "agent-good",
      agent_name: "kali-01",
      task_type: "QUICK_RECON",
      created_at: "2026-09-20T00:00:00Z",
      status: "SUCCESS",
      result: { data: { system: { hostname: "kali-01" } } },
    },
    {
      id: "task-failed",
      agent_id: "agent-failed",
      agent_name: "lab-02",
      task_type: "QUICK_RECON",
      created_at: "2026-09-20T00:00:00Z",
      completed_at: "2026-09-20T00:00:01Z",
      status: "FAILED",
      error_message: "Agent missed its deadline.",
    },
  ],
};

describe("BulkOperationPage", () => {
  it("shows partial failure state and retries failed targets through the grouped endpoint", async () => {
    vi.spyOn(api.tasks, "bulkOperation").mockResolvedValue(operation);
    const retry = vi
      .spyOn(api.tasks, "retryBulkFailed")
      .mockResolvedValue({
        ...operation,
        bulk_operation_id: "operation-retry",
        target_count: 1,
        status_counts: { ...operation.status_counts, SUCCESS: 0, FAILED: 0, QUEUED: 1 },
        tasks: [],
      });
    const user = userEvent.setup();
    renderWithContexts(
      <Routes>
        <Route path="bulk-operations/:id" element={<BulkOperationPage />} />
      </Routes>,
      { route: "/bulk-operations/operation-1" },
    );

    expect(await screen.findByText("kali-01")).toBeInTheDocument();
    expect(screen.getByText("lab-02")).toBeInTheDocument();
    expect(screen.getByText("Agent missed its deadline.")).toBeInTheDocument();
    await user.click(
      screen.getByRole("checkbox", {
        name: "Confirm authorized scope for operation actions",
      }),
    );
    await user.click(screen.getByRole("button", { name: /Retry failed/ }));
    await waitFor(() => expect(retry).toHaveBeenCalledWith("operation-1", true));
  });
});
