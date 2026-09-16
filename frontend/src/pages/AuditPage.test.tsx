import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { api } from "../services/api";
import { renderWithContexts } from "../test/render";
import { AuditPage } from "./AuditPage";

describe("AuditPage filters", () => {
  it("uses the backend's searchable user/agent and time filter parameter names", async () => {
    const list = vi.spyOn(api.audit, "list").mockResolvedValue({
      items: [],
      total: 0,
      skip: 0,
      limit: 25,
    });
    vi.spyOn(api.audit, "eventTypes").mockResolvedValue([
      "TASK_COMPLETED",
      "TASK_EXPIRED",
    ]);
    const user = userEvent.setup();
    renderWithContexts(<AuditPage />);
    await screen.findByText("No audit events match");
    expect(
      screen.getByRole("option", { name: "Task Expired" }),
    ).toBeInTheDocument();

    await user.type(
      screen.getByLabelText("Search audit log"),
      "task-42{Enter}",
    );
    await user.selectOptions(
      screen.getByLabelText("Audit event type"),
      "TASK_COMPLETED",
    );
    await user.click(screen.getByRole("button", { name: /^Filters/ }));
    fireEvent.change(screen.getByLabelText("User"), {
      target: { value: "analyst@example.local" },
    });
    fireEvent.change(screen.getByLabelText("Agent"), {
      target: { value: "sensor-07" },
    });
    fireEvent.change(screen.getByLabelText("Source IP"), {
      target: { value: "192.0.2.44" },
    });
    fireEvent.change(screen.getByLabelText("From"), {
      target: { value: "2026-09-01" },
    });
    fireEvent.change(screen.getByLabelText("Through"), {
      target: { value: "2026-09-14" },
    });

    await waitFor(() => {
      const match = list.mock.calls
        .map(([parameters]) => parameters)
        .find(
          (parameters) =>
            parameters.search === "task-42" &&
            parameters.event_type === "TASK_COMPLETED" &&
            parameters.user === "analyst@example.local" &&
            parameters.agent === "sensor-07" &&
            parameters.source_ip === "192.0.2.44" &&
            parameters.start_time &&
            parameters.end_time,
        );
      expect(match).toBeDefined();
      expect(match).not.toHaveProperty("user_id");
      expect(match).not.toHaveProperty("agent_id");
      expect(match?.start_time).toEqual(expect.any(String));
      expect(match?.end_time).toEqual(expect.any(String));
    });
  });
});
