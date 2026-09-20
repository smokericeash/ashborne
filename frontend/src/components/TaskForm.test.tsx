import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { api } from "../services/api";
import { operator, renderWithContexts, viewer } from "../test/render";
import { TASK_TYPES, type AshborneTask } from "../types";
import { TaskForm } from "./TaskForm";

const createdTask: AshborneTask = {
  id: "task-1",
  agent_id: "agent-1",
  task_type: "LISTENING_PORTS",
  parameters: {},
  requested_by_id: operator.id,
  created_at: "2026-09-14T00:00:00Z",
  status: "QUEUED",
};

describe("TaskForm", () => {
  it("offers only typed lab actions and requires an authorization confirmation", async () => {
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
      name: "Approved lab action",
    });
    expect(
      new Set(
        within(select)
          .getAllByRole("option")
          .map((option) => option.getAttribute("value")),
      ),
    ).toEqual(new Set(TASK_TYPES));
    expect(
      screen.queryByRole("textbox", { name: /command/i }),
    ).not.toBeInTheDocument();

    await user.selectOptions(select, "LISTENING_PORTS");
    const queueButton = screen.getByRole("button", {
      name: "Queue lab action",
    });
    expect(queueButton).toBeDisabled();
    await user.click(
      screen.getByRole("checkbox", {
        name: /explicitly included in the authorized lab scope/i,
      }),
    );
    await user.click(queueButton);

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith("agent-1", "LISTENING_PORTS", true),
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
      screen.queryByRole("button", { name: /queue lab action/i }),
    ).not.toBeInTheDocument();
  });
});
