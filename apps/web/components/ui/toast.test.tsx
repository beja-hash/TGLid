import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ToastProvider, useToast } from "./toast";

afterEach(cleanup);

describe("ToastProvider", () => {
  it("shows a notification once and lets the user close it", () => {
    function Trigger() {
      const { notify } = useToast();
      return (
        <button
          onClick={() => {
            notify("Сохранено");
            notify("Сохранено");
          }}
          type="button"
        >
          Показать
        </button>
      );
    }
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Показать" }));
    expect(screen.getAllByText("Сохранено")).toHaveLength(1);
    fireEvent.click(
      screen.getByRole("button", { name: "Закрыть уведомление" }),
    );
    expect(screen.queryByText("Сохранено")).toBeNull();
  });
});
