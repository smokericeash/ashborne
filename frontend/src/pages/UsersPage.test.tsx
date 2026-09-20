import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { api } from "../services/api";
import { administrator, renderWithContexts } from "../test/render";
import { UsersPage } from "./UsersPage";

describe("UsersPage creation validation", () => {
  it("matches backend display-name and password rules before creating a user", async () => {
    vi.spyOn(api.users, "list").mockResolvedValue({
      items: [],
      total: 0,
      skip: 0,
      limit: 20,
    });
    const create = vi.spyOn(api.users, "create").mockResolvedValue({
      ...administrator,
      id: "44444444-4444-4444-8444-444444444444",
      email: "analyst@example.local",
      display_name: "Security Analyst",
      role: "VIEWER",
    });
    const user = userEvent.setup();
    renderWithContexts(<UsersPage />);

    await screen.findByText("No users match");
    await user.click(screen.getByRole("button", { name: "Create user" }));
    const dialog = screen.getByRole("dialog", { name: "Create ASHBORNE user" });
    const submit = within(dialog).getByRole("button", { name: "Create user" });
    const displayName = within(dialog).getByLabelText("Display name");
    const password = within(dialog).getByLabelText("Initial password");

    await user.type(
      within(dialog).getByLabelText("Email address"),
      " Analyst@Example.Local ",
    );
    await user.type(displayName, "   ");
    await user.type(password, "ValidPassword123");
    await user.click(submit);
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Enter a display name.",
    );
    expect(create).not.toHaveBeenCalled();

    await user.clear(displayName);
    await user.type(displayName, " Security Analyst ");
    await user.clear(password);
    await user.type(password, "lowercase1234");
    await user.click(submit);
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "upper-case, lower-case, and numeric",
    );
    expect(create).not.toHaveBeenCalled();

    await user.clear(password);
    await user.type(password, "ValidPassword123");
    await user.click(submit);

    await waitFor(() =>
      expect(create).toHaveBeenCalledWith({
        email: "analyst@example.local",
        display_name: "Security Analyst",
        password: "ValidPassword123",
        role: "VIEWER",
      }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });
});
