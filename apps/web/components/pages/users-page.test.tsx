import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import UsersPage from "../../app/(protected)/users/page";
import type { UserProfile } from "../../src/lib/api/types";
import { ToastProvider } from "../ui/toast";

const user: UserProfile = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "anna@example.com",
  full_name: "Анна Смирнова",
  role: "EMPLOYEE",
  is_active: true,
  must_change_password: false,
};

const apiMocks = vi.hoisted(() => ({
  users: vi.fn(),
  createUser: vi.fn(),
  updateUser: vi.fn(),
  resetPassword: vi.fn(),
}));

vi.mock("../../src/lib/auth/context", () => ({
  useAuth: () => ({ user: { role: "ADMIN" } }),
}));
vi.mock("../../src/lib/api/client", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../src/lib/api/client")>();
  return {
    ...actual,
    api: apiMocks,
  };
});

function renderPage() {
  return render(
    <ToastProvider>
      <UsersPage />
    </ToastProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.users.mockResolvedValue({
    items: [user],
    total: 1,
    page: 1,
    page_size: 25,
  });
  apiMocks.updateUser.mockResolvedValue(user);
});

afterEach(cleanup);

describe("UsersPage", () => {
  it("renders the list and applies filters", async () => {
    apiMocks.users.mockResolvedValue({
      items: [user],
      total: 1,
      page: 1,
      page_size: 25,
    });
    renderPage();
    expect(await screen.findAllByText("Анна Смирнова")).toHaveLength(2);
    fireEvent.change(screen.getByLabelText("Поиск"), {
      target: { value: "anna" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Применить" }));
    await waitFor(() =>
      expect(apiMocks.users.mock.calls.length).toBeGreaterThan(1),
    );
    const query = apiMocks.users.mock.calls.at(-1)?.[0] as URLSearchParams;
    expect(query.get("search")).toBe("anna");
  });

  it("creates a user and shows the one-time password result", async () => {
    apiMocks.users.mockResolvedValue({
      items: [user],
      total: 1,
      page: 1,
      page_size: 25,
    });
    apiMocks.createUser.mockResolvedValue({
      user,
      temporary_password: "temporary-secret",
    });
    renderPage();
    await screen.findAllByText("Анна Смирнова");
    fireEvent.click(
      screen.getByRole("button", { name: "Добавить сотрудника" }),
    );
    fireEvent.change(screen.getByLabelText("Полное имя"), {
      target: { value: "Анна Смирнова" },
    });
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "anna@example.com" },
    });
    fireEvent.click(
      within(screen.getByRole("dialog", { name: "Новый сотрудник" })).getByRole(
        "button",
        { name: "Добавить сотрудника" },
      ),
    );
    expect(await screen.findByText("temporary-secret")).toBeTruthy();
    expect(apiMocks.createUser).toHaveBeenCalledOnce();
  });

  it("requires confirmation before resetting a password", async () => {
    apiMocks.users.mockResolvedValue({
      items: [user],
      total: 1,
      page: 1,
      page_size: 25,
    });
    apiMocks.resetPassword.mockResolvedValue({
      user,
      temporary_password: "reset-secret",
    });
    renderPage();
    await screen.findAllByText("Анна Смирнова");
    const actionMenus = screen.getAllByLabelText("Действия для Анна Смирнова");
    fireEvent.click(actionMenus[0]);
    fireEvent.click(
      screen.getAllByRole("button", { name: "Сбросить пароль" })[0],
    );
    const dialog = screen.getByRole("dialog", { name: "Сбросить пароль?" });
    expect(apiMocks.resetPassword).not.toHaveBeenCalled();
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Сбросить пароль" }),
    );
    await waitFor(() => expect(apiMocks.resetPassword).toHaveBeenCalledOnce());
  });

  it("edits a user in a dialog", async () => {
    renderPage();
    await screen.findAllByText("Анна Смирнова");
    fireEvent.click(screen.getAllByRole("button", { name: "Изменить" })[0]);
    const dialog = screen.getByRole("dialog", {
      name: "Изменить сотрудника",
    });
    fireEvent.change(within(dialog).getByLabelText("Полное имя"), {
      target: { value: "Анна Петрова" },
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Сохранить изменения" }),
    );
    await waitFor(() =>
      expect(apiMocks.updateUser).toHaveBeenCalledWith(user.id, {
        full_name: "Анна Петрова",
        role: "EMPLOYEE",
      }),
    );
  });

  it("requires confirmation before deactivation", async () => {
    renderPage();
    await screen.findAllByText("Анна Смирнова");
    fireEvent.click(
      screen.getAllByRole("button", { name: "Деактивировать" })[0],
    );
    const dialog = screen.getByRole("dialog", {
      name: "Деактивировать сотрудника?",
    });
    expect(apiMocks.updateUser).not.toHaveBeenCalled();
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Деактивировать" }),
    );
    await waitFor(() =>
      expect(apiMocks.updateUser).toHaveBeenCalledWith(user.id, {
        is_active: false,
      }),
    );
  });
});
