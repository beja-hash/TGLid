import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ProfilePage from "../../app/(protected)/profile/page";

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
      email: "admin@example.com",
      full_name: "Ирина Соколова",
      role: "ADMIN",
      is_active: true,
      must_change_password: false,
    },
  }),
}));

afterEach(cleanup);

describe("ProfilePage", () => {
  it("renders identity, role, status and security action", () => {
    render(<ProfilePage />);
    expect(screen.getAllByText("Ирина Соколова").length).toBeGreaterThan(1);
    expect(screen.getAllByText("admin@example.com").length).toBeGreaterThan(1);
    expect(screen.getByText("Администратор")).toBeTruthy();
    expect(screen.getByText("Постоянный пароль установлен")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Сменить пароль" })).toBeTruthy();
  });
});
