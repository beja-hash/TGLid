import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "./app-shell";

const mocks = vi.hoisted(() => ({
  pathname: "/",
  logout: vi.fn().mockResolvedValue(undefined),
  role: "ADMIN" as "ADMIN" | "EMPLOYEE",
}));

vi.mock("next/navigation", () => ({
  usePathname: () => mocks.pathname,
}));
vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: {
    children: React.ReactNode;
    href: string;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));
vi.mock("../../src/lib/auth/context", () => ({
  useAuth: () => ({
    user: {
      id: "1",
      email: "user@example.com",
      full_name: "Иван Петров",
      role: mocks.role,
      is_active: true,
      must_change_password: false,
    },
    logout: mocks.logout,
  }),
}));

afterEach(() => {
  cleanup();
  mocks.role = "ADMIN";
  mocks.pathname = "/";
  mocks.logout.mockClear();
  document.body.className = "";
});

describe("AppShell", () => {
  it("shows admin navigation and marks the active page", () => {
    mocks.pathname = "/users";
    render(<AppShell>Контент</AppShell>);
    expect(
      screen
        .getByRole("link", { name: "Сотрудники" })
        .getAttribute("aria-current"),
    ).toBe("page");
    expect(screen.getByRole("link", { name: "Аудит" })).toBeTruthy();
  });

  it("hides admin navigation from an employee", () => {
    mocks.role = "EMPLOYEE";
    render(<AppShell>Контент</AppShell>);
    expect(screen.queryByRole("link", { name: "Сотрудники" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Аудит" })).toBeNull();
  });

  it("opens and closes the mobile drawer", () => {
    render(<AppShell>Контент</AppShell>);
    const open = screen.getByRole("button", { name: "Открыть меню" });
    fireEvent.click(open);
    expect(open.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(screen.getAllByRole("button", { name: "Закрыть меню" })[0]);
    expect(open.getAttribute("aria-expanded")).toBe("false");
  });
});
