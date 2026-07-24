import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "../../app/(protected)/page";

const mocks = vi.hoisted(() => ({
  role: "ADMIN" as "ADMIN" | "EMPLOYEE",
  systemStatus: vi.fn(),
  telegramAccount: vi.fn(),
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
      full_name: "Анна Смирнова",
      role: mocks.role,
    },
  }),
}));
vi.mock("../../src/lib/api/client", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../src/lib/api/client")>();
  return { ...actual, api: mocks };
});

beforeEach(() => {
  mocks.role = "ADMIN";
  mocks.systemStatus.mockResolvedValue({
    api: "ok",
    postgres: "ok",
    redis: "ok",
    environment: "test",
  });
  mocks.telegramAccount.mockResolvedValue({
    configured: true,
    id: "telegram-account-id",
    telegram_user_id: 123456789,
    phone_masked: "+7******67",
    username: "safe_username",
    first_name: "Анна",
    last_name: "Смирнова",
    status: "ERROR",
    is_active: true,
    connected_at: null,
    disconnected_at: null,
    last_checked_at: null,
    last_error_code: "TELEGRAM_UNAVAILABLE",
    last_error_message: "Telegram временно недоступен",
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Dashboard Telegram status", () => {
  it("shows Telegram separately without changing the overall health", async () => {
    render(<DashboardPage />);
    expect(
      await screen.findByRole("heading", {
        name: "Все системы работают штатно",
      }),
    ).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Telegram" })).toBeTruthy();
    expect(screen.getByText("Статус аккаунта: ERROR")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Управление" })).toBeTruthy();
  });

  it("does not request or show Telegram status for an employee", async () => {
    mocks.role = "EMPLOYEE";
    render(<DashboardPage />);
    await screen.findByRole("heading", { name: "Все системы работают штатно" });
    await waitFor(() => expect(mocks.systemStatus).toHaveBeenCalledOnce());
    expect(mocks.telegramAccount).not.toHaveBeenCalled();
    expect(screen.queryByRole("heading", { name: "Telegram" })).toBeNull();
  });
});
