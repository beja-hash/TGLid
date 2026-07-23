import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../src/lib/api/client";
import { LoginForm } from "./login-form";

const login = vi.fn();
vi.mock("../../src/lib/auth/context", () => ({ useAuth: () => ({ login }) }));
afterEach(() => {
  cleanup();
  login.mockReset();
});

describe("LoginForm", () => {
  it("connects labels and redirects only after a successful login", async () => {
    login.mockResolvedValueOnce({});
    const onSuccess = vi.fn();
    render(<LoginForm onSuccess={onSuccess} />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: " admin@example.com " },
    });
    fireEvent.change(screen.getByLabelText("Пароль"), {
      target: { value: "password" },
    });
    fireEvent.submit(
      screen.getByRole("button", { name: "Войти" }).closest("form")!,
    );
    await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce());
    expect(login).toHaveBeenCalledWith("admin@example.com", "password");
  });

  it("shows generic 401 and blocks a duplicate submission", async () => {
    let resolve!: () => void;
    login.mockImplementationOnce(
      () =>
        new Promise<void>((done) => {
          resolve = done;
        }),
    );
    const view = render(<LoginForm onSuccess={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "a@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Пароль"), {
      target: { value: "bad" },
    });
    const form = view.getByRole("button", { name: "Войти" }).closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(login).toHaveBeenCalledOnce();
    resolve();
  });

  it("shows safe rate-limit and temporary-service messages", async () => {
    login.mockRejectedValueOnce(
      new ApiError(429, "RATE_LIMITED", "hidden", 15),
    );
    const view = render(<LoginForm onSuccess={vi.fn()} />);
    fireEvent.change(view.getByLabelText("Email"), {
      target: { value: "a@example.com" },
    });
    fireEvent.change(view.getByLabelText("Пароль"), {
      target: { value: "bad" },
    });
    fireEvent.submit(
      view.getByRole("button", { name: "Войти" }).closest("form")!,
    );
    expect((await view.findByRole("alert")).textContent).toContain("15 секунд");
  });
});
