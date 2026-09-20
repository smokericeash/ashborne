import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
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
    renderWithContexts(<StructuredResult task={task} />);

    expect(screen.getByRole("columnheader", { name: "Interface" })).toBeInTheDocument();
    expect(screen.getByText("eth0")).toBeInTheDocument();
    expect(screen.getByText("172.22.0.5")).toBeInTheDocument();
    expect(screen.queryByText(/"interfaces"/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Raw/ }));
    expect(screen.getByText(/"interfaces"/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Timeline/ }));
    expect(screen.getByText("Created")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });
});
