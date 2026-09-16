import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Button, Modal } from "./ui";

function ModalHarness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Open details</button>
      <Modal
        open={open}
        title="Diagnostic details"
        description="Review the structured result."
        onClose={() => setOpen(false)}
      >
        <div className="p-4">
          <Button>Confirm</Button>
        </div>
      </Modal>
    </>
  );
}

describe("Modal accessibility", () => {
  it("labels, traps, and restores focus while supporting Escape", async () => {
    const user = userEvent.setup();
    render(<ModalHarness />);

    const trigger = screen.getByRole("button", { name: "Open details" });
    await user.click(trigger);

    const dialog = screen.getByRole("dialog", {
      name: "Diagnostic details",
      description: "Review the structured result.",
    });
    expect(dialog).toHaveFocus();
    expect(document.body).toHaveStyle({ overflow: "hidden" });

    const close = screen.getByRole("button", { name: "Close dialog" });
    const confirm = screen.getByRole("button", { name: "Confirm" });
    confirm.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(close).toHaveFocus();
    close.focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(confirm).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(document.body).not.toHaveStyle({ overflow: "hidden" });
  });

  it("only closes from the overlay itself", () => {
    const onClose = vi.fn();
    render(
      <Modal open title="Details" onClose={onClose}>
        <p>Content</p>
      </Modal>,
    );

    fireEvent.mouseDown(screen.getByText("Content"));
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.mouseDown(screen.getByRole("dialog"));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
