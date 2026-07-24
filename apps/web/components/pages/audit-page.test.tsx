import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AuditPage from "../../app/(protected)/audit/page";
import type { AuditLog } from "../../src/lib/api/types";

const event: AuditLog = {
  id: "event-full-uuid",
  actor_user_id: "11111111-1111-4111-8111-111111111111",
  event_type: "AUTH_LOGIN_SUCCEEDED",
  target_type: "user",
  target_id: "22222222-2222-4222-8222-222222222222",
  ip_address: "127.0.0.1",
  user_agent: "Test Browser",
  metadata: { source: "test" },
  created_at: "2026-07-23T12:00:00Z",
};

const apiMocks = vi.hoisted(() => ({
  auditLogs: vi.fn(),
}));

vi.mock("../../src/lib/auth/context", () => ({
  useAuth: () => ({ user: { role: "ADMIN" } }),
}));
vi.mock("../../src/lib/api/client", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../src/lib/api/client")>();
  return { ...actual, api: apiMocks };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AuditPage", () => {
  it("renders readable events and structured details", async () => {
    apiMocks.auditLogs.mockResolvedValue({
      items: [event],
      total: 1,
      page: 1,
      page_size: 50,
    });
    render(<AuditPage />);
    await waitFor(() =>
      expect(screen.getAllByText("Успешный вход").length).toBeGreaterThan(1),
    );
    expect(screen.getAllByText("Успешный вход").length).toBeGreaterThan(1);
    fireEvent.click(screen.getAllByRole("button", { name: "Подробнее" })[0]);
    expect(screen.getByRole("dialog", { name: "Успешный вход" })).toBeTruthy();
    expect(
      screen.getByText("11111111-1111-4111-8111-111111111111"),
    ).toBeTruthy();
    expect(screen.getByText("Test Browser")).toBeTruthy();
    expect(screen.getByText("source")).toBeTruthy();
  });

  it("applies a known event filter", async () => {
    apiMocks.auditLogs.mockResolvedValue({
      items: [event],
      total: 1,
      page: 1,
      page_size: 50,
    });
    render(<AuditPage />);
    await screen.findAllByText("Успешный вход");
    fireEvent.change(screen.getByLabelText("Событие"), {
      target: { value: "AUTH_LOGIN_SUCCEEDED" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Применить" }));
    await waitFor(() =>
      expect(apiMocks.auditLogs.mock.calls.length).toBeGreaterThan(1),
    );
    const query = apiMocks.auditLogs.mock.calls.at(-1)?.[0] as URLSearchParams;
    expect(query.get("event_type")).toBe("AUTH_LOGIN_SUCCEEDED");
  });

  it("shows a dedicated empty state", async () => {
    apiMocks.auditLogs.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 50,
    });
    render(<AuditPage />);
    expect(await screen.findByText("Журнал пока пуст")).toBeTruthy();
  });

  it("maps Telegram lifecycle events to safe readable labels", async () => {
    apiMocks.auditLogs.mockResolvedValue({
      items: [
        {
          ...event,
          id: "telegram-event-id",
          event_type: "TELEGRAM_SESSION_REMOVED",
          target_type: "telegram_account",
          metadata: {},
        },
      ],
      total: 1,
      page: 1,
      page_size: 50,
    });
    render(<AuditPage />);
    expect(
      (await screen.findAllByText("Сессия Telegram удалена")).length,
    ).toBeGreaterThan(0);
  });
});
