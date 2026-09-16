import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { api } from "../services/api";
import { renderWithContexts } from "../test/render";
import type { KandorSettings } from "../types";
import { SettingsPage } from "./SettingsPage";

const backendSettings: KandorSettings = {
  heartbeat_interval_seconds: 30,
  degraded_threshold_seconds: 60,
  offline_threshold_seconds: 300,
  task_expiration_seconds: 3600,
  session_timeout_minutes: 60,
  page_size: 50,
  audit_retention_days: 365,
};

describe("SettingsPage contract", () => {
  it("loads and updates the exact page_size field with API bounds", async () => {
    vi.spyOn(api.settings, "get").mockResolvedValue(backendSettings);
    const update = vi
      .spyOn(api.settings, "update")
      .mockImplementation(async (value) => value);
    vi.spyOn(api.enrollment, "list").mockResolvedValue({
      items: [],
      total: 0,
      skip: 0,
      limit: 50,
    });
    const user = userEvent.setup();
    renderWithContexts(<SettingsPage />);

    const pageSize = await screen.findByLabelText(/Default page size/i);
    expect(pageSize).toHaveValue(50);
    expect(pageSize).toHaveAttribute("min", "1");
    expect(pageSize).toHaveAttribute("max", "500");
    expect(screen.getByLabelText(/Session timeout/i)).toHaveAttribute(
      "max",
      "1440",
    );

    fireEvent.change(pageSize, { target: { value: "275" } });
    await user.click(
      screen.getByRole("button", { name: "Save configuration" }),
    );

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith({
        ...backendSettings,
        page_size: 275,
      }),
    );
    expect(screen.getByLabelText(/Default page size/i)).toHaveValue(275);
  });
});
