import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { api } from "../services/api";
import { operator, renderWithContexts, viewer } from "../test/render";
import { TASK_TYPES, type KandorTask } from "../types";
import { TaskForm } from "./TaskForm";

const createdTask: KandorTask = {
  id: "task-1",
  agent_id: "agent-1",
  task_type: "LISTENING_PORTS",
  parameters: {},
  requested_by_id: operator.id,
  created_at: "2026-09-14T00:00:00Z",
  status: "QUEUED",
};

describe("TaskForm", () => {
  it("offers only allowlisted task enums and queues the selected diagnostic", async () => {
    const create = vi.spyOn(api.tasks, "create").mockResolvedValue(createdTask);
    const onCreated = vi.fn();
    const user = userEvent.setup();
    renderWithContexts(
      <TaskForm
        agentId="agent-1"
        agentName="lab-agent"
        onCreated={onCreated}
      />,
      { user: operator },
    );

    const select = screen.getByRole("combobox", {
      name: "Approved diagnostic task",
    });
    expect(
      within(select)
        .getAllByRole("option")
        .map((option) => option.getAttribute("value")),
    ).toEqual([...TASK_TYPES]);
    expect(
      screen.queryByRole("textbox", { name: /command/i }),
    ).not.toBeInTheDocument();

    await user.selectOptions(select, "LISTENING_PORTS");
    await user.click(screen.getByRole("button", { name: "Queue diagnostic" }));

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith("agent-1", "LISTENING_PORTS"),
    );
    expect(onCreated).toHaveBeenCalledWith(createdTask);
  });

  it("renders a read-only denial for viewers and no task controls", () => {
    renderWithContexts(<TaskForm agentId="agent-1" agentName="lab-agent" />, {
      user: viewer,
    });

    expect(screen.getByText("Read-only role")).toBeInTheDocument();
    expect(
      screen.getByText(/cannot issue work to agents/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /queue diagnostic/i }),
    ).not.toBeInTheDocument();
  });
});
