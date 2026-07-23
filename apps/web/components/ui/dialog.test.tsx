import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Dialog } from "./dialog";

afterEach(cleanup);

describe("Dialog", () => {
  it("closes on Escape and returns focus to the trigger", () => {
    const onClose = vi.fn();
    const trigger = document.createElement("button");
    trigger.textContent = "Открыть";
    document.body.appendChild(trigger);
    trigger.focus();
    const view = render(
      <Dialog onClose={onClose} open title="Диалог">
        <button type="button">Действие</button>
      </Dialog>,
    );
    expect(screen.getByRole("dialog")).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
    view.unmount();
    expect(document.activeElement).toBe(trigger);
    trigger.remove();
  });
});
