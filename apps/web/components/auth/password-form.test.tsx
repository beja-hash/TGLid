import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PasswordForm } from "./password-form";

afterEach(cleanup);

describe("PasswordForm", () => {
  it("rejects a mismatched confirmation without calling backend", () => {
    const submit = vi.fn();
    render(<PasswordForm onSubmit={submit} />);
    fireEvent.change(screen.getByLabelText("Текущий пароль"), {
      target: { value: "old-password" },
    });
    fireEvent.change(screen.getByLabelText("Новый пароль"), {
      target: { value: "new-password" },
    });
    fireEvent.change(screen.getByLabelText("Подтвердите новый пароль"), {
      target: { value: "different" },
    });
    fireEvent.submit(
      screen.getByRole("button", { name: "Сменить пароль" }).closest("form")!,
    );
    expect(screen.getByRole("alert").textContent).toContain("не совпадает");
    expect(submit).not.toHaveBeenCalled();
  });

  it("submits matching values and clears fields", async () => {
    const submit = vi.fn().mockResolvedValue(undefined);
    const view = render(<PasswordForm onSubmit={submit} />);
    fireEvent.change(view.getByLabelText("Текущий пароль"), {
      target: { value: "old-password" },
    });
    fireEvent.change(view.getByLabelText("Новый пароль"), {
      target: { value: "a long new password" },
    });
    fireEvent.change(view.getByLabelText("Подтвердите новый пароль"), {
      target: { value: "a long new password" },
    });
    fireEvent.submit(
      view.getByRole("button", { name: "Сменить пароль" }).closest("form")!,
    );
    await waitFor(() =>
      expect(submit).toHaveBeenCalledWith(
        "old-password",
        "a long new password",
      ),
    );
    expect(view.getByRole("status").textContent).toContain("успешно");
    expect(
      (view.getByLabelText("Текущий пароль") as HTMLInputElement).value,
    ).toBe("");
  });
});
