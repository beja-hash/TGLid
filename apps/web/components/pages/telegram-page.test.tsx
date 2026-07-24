import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TelegramPage from "./telegram-page";
import { ApiError } from "../../src/lib/api/client";
import type {
  TelegramAccount,
  TelegramAuthChallenge,
} from "../../src/lib/api/types";

const mocks = vi.hoisted(() => ({
  checkTelegram: vi.fn(),
  connectTelegram: vi.fn(),
  disconnectTelegram: vi.fn(),
  notify: vi.fn(),
  removeTelegramSession: vi.fn(),
  role: "ADMIN" as "ADMIN" | "EMPLOYEE",
  startTelegramAuth: vi.fn(),
  telegramAccount: vi.fn(),
  verifyTelegramCode: vi.fn(),
  verifyTelegramPassword: vi.fn(),
}));

vi.mock("../../src/lib/auth/context", () => ({
  useAuth: () => ({ user: { role: mocks.role } }),
}));
vi.mock("../../src/lib/api/client", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../src/lib/api/client")>();
  return { ...actual, api: mocks };
});
vi.mock("../ui/toast", () => ({
  useToast: () => ({ notify: mocks.notify }),
}));

const noAccount: TelegramAccount = {
  configured: true,
  id: null,
  telegram_user_id: null,
  phone_masked: null,
  username: null,
  first_name: null,
  last_name: null,
  status: "DISCONNECTED",
  is_active: false,
  connected_at: null,
  disconnected_at: null,
  last_checked_at: null,
  last_error_code: null,
  last_error_message: null,
};

const disconnected: TelegramAccount = {
  configured: true,
  id: "telegram-account-id",
  telegram_user_id: 123456789,
  phone_masked: "+7******67",
  username: "safe_username",
  first_name: "Анна",
  last_name: "Смирнова",
  status: "DISCONNECTED",
  is_active: true,
  connected_at: null,
  disconnected_at: "2026-07-24T09:00:00Z",
  last_checked_at: null,
  last_error_code: null,
  last_error_message: null,
};

const connected: TelegramAccount = {
  ...disconnected,
  status: "CONNECTED",
  connected_at: "2026-07-24T09:05:00Z",
  last_checked_at: "2026-07-24T09:06:00Z",
};

const codeChallenge: TelegramAuthChallenge = {
  challenge_id: "challenge-code-id-12345678901234567890",
  status: "AUTH_CODE_REQUIRED",
  phone_masked: "+7******67",
};

const passwordChallenge: TelegramAuthChallenge = {
  ...codeChallenge,
  status: "AUTH_PASSWORD_REQUIRED",
};

function beginAuth(): void {
  fireEvent.click(screen.getByRole("button", { name: "Авторизовать аккаунт" }));
  fireEvent.change(screen.getByLabelText("Номер телефона"), {
    target: { value: "+79990000067" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Получить код" }));
}

beforeEach(() => {
  mocks.role = "ADMIN";
  mocks.telegramAccount.mockResolvedValue(noAccount);
  mocks.startTelegramAuth.mockResolvedValue(codeChallenge);
  mocks.verifyTelegramCode.mockResolvedValue({
    ...codeChallenge,
    status: "DISCONNECTED",
  });
  mocks.verifyTelegramPassword.mockResolvedValue({
    ...passwordChallenge,
    status: "DISCONNECTED",
  });
  mocks.connectTelegram.mockResolvedValue(connected);
  mocks.disconnectTelegram.mockResolvedValue(disconnected);
  mocks.checkTelegram.mockResolvedValue(connected);
  mocks.removeTelegramSession.mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  document.body.className = "";
});

describe("TelegramPage", () => {
  it("is ADMIN-only", () => {
    mocks.role = "EMPLOYEE";
    render(<TelegramPage />);
    expect(
      screen.getByRole("heading", { name: "Недостаточно прав" }),
    ).toBeTruthy();
    expect(mocks.telegramAccount).not.toHaveBeenCalled();
  });

  it("renders NOT_CONFIGURED without breaking the page", async () => {
    mocks.telegramAccount.mockResolvedValue({
      ...noAccount,
      configured: false,
      status: "NOT_CONFIGURED",
    });
    render(<TelegramPage />);
    expect(
      await screen.findByRole("heading", { name: "Telegram не настроен" }),
    ).toBeTruthy();
    expect(screen.getByText("NOT_CONFIGURED")).toBeTruthy();
  });

  it("renders an empty account and starts the code flow", async () => {
    render(<TelegramPage />);
    expect(await screen.findByText("Аккаунт не авторизован")).toBeTruthy();
    beginAuth();
    expect(
      await screen.findByRole("heading", { name: "Введите код" }),
    ).toBeTruthy();
    expect(mocks.startTelegramAuth).toHaveBeenCalledWith("+79990000067");
    expect(screen.getByText(/Код отправлен на \+7\*{6}67/)).toBeTruthy();
  });

  it("shows an invalid-code error and clears the submitted code", async () => {
    mocks.verifyTelegramCode.mockRejectedValue(
      new ApiError(400, "PHONE_CODE_INVALID", "Неверный код"),
    );
    render(<TelegramPage />);
    await screen.findByText("Аккаунт не авторизован");
    beginAuth();
    await screen.findByRole("heading", { name: "Введите код" });
    const input = screen.getByLabelText("Код Telegram") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "12345" } });
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить код" }));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Неверный код",
    );
    expect(input.value).toBe("");
  });

  it("moves to 2FA, clears the phone and clears an invalid password", async () => {
    mocks.verifyTelegramCode.mockResolvedValue(passwordChallenge);
    mocks.verifyTelegramPassword.mockRejectedValue(
      new ApiError(400, "PASSWORD_HASH_INVALID", "Неверный пароль 2FA"),
    );
    render(<TelegramPage />);
    await screen.findByText("Аккаунт не авторизован");
    beginAuth();
    await screen.findByRole("heading", { name: "Введите код" });
    fireEvent.change(screen.getByLabelText("Код Telegram"), {
      target: { value: "24680" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить код" }));
    expect(
      await screen.findByRole("heading", { name: "Введите пароль 2FA" }),
    ).toBeTruthy();
    expect(screen.queryByDisplayValue("+79990000067")).toBeNull();
    const password = screen.getByLabelText("Пароль 2FA") as HTMLInputElement;
    fireEvent.change(password, { target: { value: "temporary-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить 2FA" }));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Неверный пароль 2FA",
    );
    expect(password.value).toBe("");
  });

  it("finishes authentication and clears the dialog state", async () => {
    mocks.telegramAccount
      .mockResolvedValueOnce(noAccount)
      .mockResolvedValueOnce(disconnected);
    render(<TelegramPage />);
    await screen.findByText("Аккаунт не авторизован");
    beginAuth();
    await screen.findByRole("heading", { name: "Введите код" });
    fireEvent.change(screen.getByLabelText("Код Telegram"), {
      target: { value: "24680" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить код" }));
    expect(await screen.findByText("@safe_username")).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(mocks.notify).toHaveBeenCalledWith("Telegram-аккаунт авторизован");
  });

  it("renders CONNECTED and supports check, disconnect and reconnect", async () => {
    mocks.telegramAccount.mockResolvedValue(connected);
    render(<TelegramPage />);
    expect(await screen.findByText("@safe_username")).toBeTruthy();
    expect(screen.getAllByText("Подключён").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Проверить" }));
    await waitFor(() => expect(mocks.checkTelegram).toHaveBeenCalledOnce());

    fireEvent.click(screen.getByRole("button", { name: "Переподключить" }));
    await waitFor(() =>
      expect(mocks.disconnectTelegram).toHaveBeenCalledOnce(),
    );
    expect(mocks.connectTelegram).toHaveBeenCalledOnce();

    mocks.disconnectTelegram.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Отключить" }));
    await waitFor(() =>
      expect(mocks.disconnectTelegram).toHaveBeenCalledOnce(),
    );
  });

  it("connects a disconnected account", async () => {
    mocks.telegramAccount.mockResolvedValue(disconnected);
    render(<TelegramPage />);
    await screen.findByText("@safe_username");
    fireEvent.click(screen.getByRole("button", { name: "Подключить" }));
    await waitFor(() => expect(mocks.connectTelegram).toHaveBeenCalledOnce());
    expect(screen.getAllByText("Подключён").length).toBeGreaterThan(0);
  });

  it("requires explicit confirmation before deleting the session", async () => {
    mocks.telegramAccount
      .mockResolvedValueOnce(connected)
      .mockResolvedValueOnce(noAccount);
    render(<TelegramPage />);
    await screen.findByText("@safe_username");
    fireEvent.click(
      screen.getByRole("button", { name: "Удалить подключение" }),
    );
    expect(screen.getByText(/потребуется повторная авторизация/i)).toBeTruthy();
    expect(mocks.removeTelegramSession).not.toHaveBeenCalled();
    const buttons = screen.getAllByRole("button", {
      name: "Удалить подключение",
    });
    fireEvent.click(buttons.at(-1)!);
    await waitFor(() =>
      expect(mocks.removeTelegramSession).toHaveBeenCalledOnce(),
    );
    expect(await screen.findByText("Аккаунт не авторизован")).toBeTruthy();
  });

  it("shows FloodWait and generic API errors safely", async () => {
    mocks.telegramAccount.mockResolvedValue(disconnected);
    mocks.connectTelegram.mockRejectedValueOnce(
      new ApiError(429, "FLOOD_WAIT", "Internal details", 45),
    );
    render(<TelegramPage />);
    await screen.findByText("@safe_username");
    fireEvent.click(screen.getByRole("button", { name: "Подключить" }));
    expect(
      await screen.findByText(
        "Telegram ограничил запросы. Повторите через 45 сек.",
      ),
    ).toBeTruthy();

    mocks.connectTelegram.mockRejectedValueOnce(
      new ApiError(503, "TELEGRAM_UNAVAILABLE", "Internal traceback"),
    );
    fireEvent.click(screen.getByRole("button", { name: "Подключить" }));
    expect(
      await screen.findByText("Telegram временно недоступен. Повторите позже."),
    ).toBeTruthy();
    expect(screen.queryByText("Internal traceback")).toBeNull();
  });

  it("clears challenge and inputs when the dialog closes", async () => {
    render(<TelegramPage />);
    await screen.findByText("Аккаунт не авторизован");
    beginAuth();
    await screen.findByRole("heading", { name: "Введите код" });
    fireEvent.change(screen.getByLabelText("Код Telegram"), {
      target: { value: "24680" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Авторизовать аккаунт" }),
    );
    expect(
      (screen.getByLabelText("Номер телефона") as HTMLInputElement).value,
    ).toBe("");
    expect(screen.queryByText(codeChallenge.challenge_id)).toBeNull();
  });

  it("keeps the dialog and account actions usable at a 390 px viewport", async () => {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 390,
    });
    window.dispatchEvent(new Event("resize"));
    render(<TelegramPage />);
    await screen.findByText("Аккаунт не авторизован");
    fireEvent.click(
      screen.getByRole("button", { name: "Авторизовать аккаунт" }),
    );
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByLabelText("Номер телефона")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Получить код" })).toBeTruthy();
  });
});
