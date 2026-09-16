import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderWithContexts } from "../../test/render";
import { Sidebar } from "./Sidebar";

describe("Sidebar accessibility", () => {
  it("removes the closed mobile navigation from keyboard and assistive access", async () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({
        matches: false,
        media: "(min-width: 1024px)",
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    );
    const onClose = vi.fn();
    const view = renderWithContexts(<Sidebar open={false} onClose={onClose} />);
    const aside = view.container.querySelector("aside");

    expect(aside).toHaveAttribute("aria-hidden", "true");
    expect(aside).toHaveAttribute("inert");

    view.unmount();
    const openView = renderWithContexts(<Sidebar open onClose={onClose} />);
    const openAside = openView.container.querySelector("aside");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Close menu" })).toHaveFocus(),
    );
    expect(openAside).not.toHaveAttribute("aria-hidden");
    expect(openAside).not.toHaveAttribute("inert");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });
});
