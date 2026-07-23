import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RequireAdmin, RequireAuth } from "./route-guards";

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  state: "authenticated" as
    | "authenticated"
    | "anonymous"
    | "loading"
    | "unavailable",
  pathname: "/users",
  role: "ADMIN" as "ADMIN" | "EMPLOYEE",
  mustChange: false,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => mocks.pathname,
  useRouter: () => ({ replace: mocks.replace }),
}));
vi.mock("../../src/lib/auth/context", () => ({
  useAuth: () => ({
    state: mocks.state,
    user:
      mocks.state === "authenticated"
        ? {
            role: mocks.role,
            must_change_password: mocks.mustChange,
          }
        : null,
  }),
}));

afterEach(() => {
  cleanup();
  mocks.replace.mockClear();
  mocks.state = "authenticated";
  mocks.role = "ADMIN";
  mocks.mustChange = false;
  mocks.pathname = "/users";
});

describe("route guards", () => {
  it("redirects anonymous visitors to login", async () => {
    mocks.state = "anonymous";
    render(<RequireAuth>Контент</RequireAuth>);
    await waitFor(() =>
      expect(mocks.replace).toHaveBeenCalledWith("/login?next=%2Fusers"),
    );
  });

  it("forces a temporary-password change", async () => {
    mocks.mustChange = true;
    render(<RequireAuth>Контент</RequireAuth>);
    await waitFor(() =>
      expect(mocks.replace).toHaveBeenCalledWith("/change-password"),
    );
  });

  it("shows a forbidden state to employees", () => {
    mocks.role = "EMPLOYEE";
    render(<RequireAdmin>Секрет</RequireAdmin>);
    expect(
      screen.getByRole("heading", { name: "Недостаточно прав" }),
    ).toBeTruthy();
    expect(screen.queryByText("Секрет")).toBeNull();
  });
});
