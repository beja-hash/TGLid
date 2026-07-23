"use client";

import {
  Edit3,
  KeyRound,
  MoreHorizontal,
  Plus,
  Power,
  RotateCcw,
  Search,
  UserRound,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { RequireAdmin } from "../../../components/auth/route-guards";
import { TemporaryPassword } from "../../../components/users/temporary-password";
import { Button } from "../../../components/ui/button";
import { ConfirmationDialog, Dialog } from "../../../components/ui/dialog";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  FormField,
  PageHeader,
  Pagination,
  Skeleton,
  StatusBadge,
} from "../../../components/ui/primitives";
import { useToast } from "../../../components/ui/toast";
import { ApiError, api } from "../../../src/lib/api/client";
import type {
  Role,
  UserProfile,
  UserWithTemporaryPassword,
} from "../../../src/lib/api/types";

const pageSize = 25;
type Filters = {
  search: string;
  role: "" | Role;
  active: "" | "true" | "false";
};
type Confirmation = {
  kind: "reset" | "deactivate";
  user: UserProfile;
} | null;

function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 409)
    return "Нельзя изменить последнего активного администратора.";
  if (error instanceof ApiError && error.status === 503)
    return "Сервис сотрудников временно недоступен.";
  return error instanceof ApiError
    ? error.message
    : "Не удалось выполнить операцию.";
}

function formatDate(value?: string | null): string {
  if (!value) return "Нет данных";
  return new Date(value).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function UsersPage() {
  return (
    <RequireAdmin>
      <UsersContent />
    </RequireAdmin>
  );
}

function UsersContent() {
  const [items, setItems] = useState<UserProfile[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [draftFilters, setDraftFilters] = useState<Filters>({
    search: "",
    role: "",
    active: "",
  });
  const [filters, setFilters] = useState<Filters>(draftFilters);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<UserProfile | null>(null);
  const [confirmation, setConfirmation] = useState<Confirmation>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [temporary, setTemporary] = useState<UserWithTemporaryPassword | null>(
    null,
  );
  const { notify } = useToast();

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    const query = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    if (filters.search.trim()) query.set("search", filters.search.trim());
    if (filters.role) query.set("role", filters.role);
    if (filters.active) query.set("is_active", filters.active);
    try {
      const result = await api.users(query);
      setItems(result.items);
      setTotal(result.total);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [filters, page]);

  useEffect(() => {
    void load();
  }, [load]);

  const create = async (payload: {
    email: string;
    full_name: string;
    role: Role;
  }): Promise<void> => {
    try {
      const result = await api.createUser(payload);
      setCreateOpen(false);
      setTemporary(result);
      notify("Сотрудник создан");
      await load();
    } catch (reason) {
      throw new Error(errorMessage(reason));
    }
  };

  const update = async (
    user: UserProfile,
    payload: Partial<Pick<UserProfile, "full_name" | "role" | "is_active">>,
  ): Promise<void> => {
    setPendingId(user.id);
    try {
      await api.updateUser(user.id, payload);
      setEditing(null);
      notify("Данные сотрудника обновлены");
      await load();
    } catch (reason) {
      const message = errorMessage(reason);
      setError(message);
      notify(message, "error");
      throw reason;
    } finally {
      setPendingId(null);
    }
  };

  const confirmAction = async (): Promise<void> => {
    if (!confirmation) return;
    const { user, kind } = confirmation;
    setPendingId(user.id);
    try {
      if (kind === "reset") {
        const result = await api.resetPassword(user.id);
        setTemporary(result);
        notify("Пароль сотрудника сброшен");
      } else {
        await api.updateUser(user.id, { is_active: false });
        notify("Сотрудник деактивирован");
      }
      setConfirmation(null);
      await load();
    } catch (reason) {
      const message = errorMessage(reason);
      setError(message);
      notify(message, "error");
    } finally {
      setPendingId(null);
    }
  };

  const activate = async (user: UserProfile): Promise<void> => {
    try {
      await update(user, { is_active: true });
      notify("Доступ сотрудника восстановлен");
    } catch {
      // Ошибка уже отражена локально и в toast.
    }
  };

  const applyFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPage(1);
    setFilters(draftFilters);
  };
  const clearFilters = () => {
    const empty: Filters = { search: "", role: "", active: "" };
    setDraftFilters(empty);
    setFilters(empty);
    setPage(1);
  };
  const hasFilters = Boolean(filters.search || filters.role || filters.active);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Управление доступом"
        title="Сотрудники"
        description={`${total} ${total === 1 ? "сотрудник" : "сотрудников"} в рабочей области`}
        actions={
          <Button onClick={() => setCreateOpen(true)} type="button">
            <Plus size={18} /> Добавить сотрудника
          </Button>
        }
      />

      <Card className="filters-card">
        <form className="filter-bar users-filters" onSubmit={applyFilters}>
          <FormField
            className="filter-search"
            htmlFor="users-search"
            label="Поиск"
          >
            <div className="input-with-icon">
              <Search size={17} aria-hidden="true" />
              <input
                id="users-search"
                onChange={(event) =>
                  setDraftFilters((current) => ({
                    ...current,
                    search: event.target.value,
                  }))
                }
                placeholder="Имя или email"
                value={draftFilters.search}
              />
            </div>
          </FormField>
          <FormField htmlFor="users-role" label="Роль">
            <select
              id="users-role"
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  role: event.target.value as "" | Role,
                }))
              }
              value={draftFilters.role}
            >
              <option value="">Все роли</option>
              <option value="ADMIN">Администратор</option>
              <option value="EMPLOYEE">Сотрудник</option>
            </select>
          </FormField>
          <FormField htmlFor="users-active" label="Статус">
            <select
              id="users-active"
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  active: event.target.value as "" | "true" | "false",
                }))
              }
              value={draftFilters.active}
            >
              <option value="">Все статусы</option>
              <option value="true">Активные</option>
              <option value="false">Неактивные</option>
            </select>
          </FormField>
          <div className="filter-actions">
            <Button type="submit" variant="secondary">
              Применить
            </Button>
            <Button
              disabled={!hasFilters && !draftFilters.search}
              onClick={clearFilters}
              type="button"
              variant="ghost"
            >
              <RotateCcw size={16} /> Сбросить
            </Button>
          </div>
        </form>
      </Card>

      <Card className="data-card">
        {loading ? (
          <Skeleton lines={6} compact />
        ) : error ? (
          <ErrorState description={error} onRetry={() => void load()} />
        ) : items.length === 0 ? (
          <EmptyState
            action={
              hasFilters ? (
                <Button
                  onClick={clearFilters}
                  type="button"
                  variant="secondary"
                >
                  Очистить фильтры
                </Button>
              ) : undefined
            }
            description={
              hasFilters
                ? "Измените запрос или сбросьте фильтры."
                : "Добавьте первого сотрудника в рабочую область."
            }
            title={hasFilters ? "Ничего не найдено" : "Список пока пуст"}
          />
        ) : (
          <UsersList
            items={items}
            onActivate={(user) => void activate(user)}
            onDeactivate={(user) =>
              setConfirmation({ kind: "deactivate", user })
            }
            onEdit={setEditing}
            onReset={(user) => setConfirmation({ kind: "reset", user })}
            pendingId={pendingId}
          />
        )}
        <Pagination
          onPage={setPage}
          page={page}
          pageSize={pageSize}
          total={total}
        />
      </Card>

      <UserFormDialog
        mode="create"
        onClose={() => setCreateOpen(false)}
        onCreate={create}
        open={createOpen}
      />
      <UserFormDialog
        mode="edit"
        onClose={() => setEditing(null)}
        onUpdate={async (payload) => {
          if (editing) await update(editing, payload);
        }}
        open={Boolean(editing)}
        pending={pendingId === editing?.id}
        user={editing ?? undefined}
      />
      <ConfirmationDialog
        confirmLabel={
          confirmation?.kind === "reset" ? "Сбросить пароль" : "Деактивировать"
        }
        danger
        description={
          confirmation?.kind === "reset"
            ? `Все сессии ${confirmation.user.full_name} будут завершены, а текущий пароль перестанет работать.`
            : `${confirmation?.user.full_name ?? "Сотрудник"} потеряет доступ, активные сессии будут завершены.`
        }
        onClose={() => setConfirmation(null)}
        onConfirm={() => void confirmAction()}
        open={Boolean(confirmation)}
        pending={pendingId === confirmation?.user.id}
        title={
          confirmation?.kind === "reset"
            ? "Сбросить пароль?"
            : "Деактивировать сотрудника?"
        }
      />
      {temporary && (
        <TemporaryPassword
          onClose={() => setTemporary(null)}
          result={temporary}
        />
      )}
    </div>
  );
}

function UsersList({
  items,
  pendingId,
  onEdit,
  onReset,
  onDeactivate,
  onActivate,
}: Readonly<{
  items: UserProfile[];
  pendingId: string | null;
  onEdit: (user: UserProfile) => void;
  onReset: (user: UserProfile) => void;
  onDeactivate: (user: UserProfile) => void;
  onActivate: (user: UserProfile) => void;
}>) {
  return (
    <>
      <div className="desktop-table">
        <table>
          <thead>
            <tr>
              <th>Сотрудник</th>
              <th>Роль</th>
              <th>Статус</th>
              <th>Пароль</th>
              <th>Последний вход</th>
              <th>Создан</th>
              <th>
                <span className="visually-hidden">Действия</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((user) => (
              <tr key={user.id}>
                <td>
                  <div className="person-cell">
                    <span className="mini-avatar" aria-hidden="true">
                      {user.full_name.slice(0, 1).toUpperCase()}
                    </span>
                    <div>
                      <strong>{user.full_name}</strong>
                      <span>{user.email}</span>
                    </div>
                  </div>
                </td>
                <td>
                  <Badge tone={user.role === "ADMIN" ? "accent" : "neutral"}>
                    {user.role === "ADMIN" ? "Администратор" : "Сотрудник"}
                  </Badge>
                </td>
                <td>
                  <StatusBadge active={user.is_active} />
                </td>
                <td>
                  <Badge
                    tone={user.must_change_password ? "warning" : "success"}
                  >
                    {user.must_change_password ? "Нужно сменить" : "Постоянный"}
                  </Badge>
                </td>
                <td className="muted-cell">{formatDate(user.last_login_at)}</td>
                <td className="muted-cell">{formatDate(user.created_at)}</td>
                <td>
                  <UserActions
                    disabled={pendingId === user.id}
                    onActivate={() => onActivate(user)}
                    onDeactivate={() => onDeactivate(user)}
                    onEdit={() => onEdit(user)}
                    onReset={() => onReset(user)}
                    user={user}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mobile-cards">
        {items.map((user) => (
          <article className="mobile-data-card" key={user.id}>
            <header>
              <div className="person-cell">
                <span className="mini-avatar" aria-hidden="true">
                  {user.full_name.slice(0, 1).toUpperCase()}
                </span>
                <div>
                  <strong>{user.full_name}</strong>
                  <span>{user.email}</span>
                </div>
              </div>
              <UserActions
                disabled={pendingId === user.id}
                onActivate={() => onActivate(user)}
                onDeactivate={() => onDeactivate(user)}
                onEdit={() => onEdit(user)}
                onReset={() => onReset(user)}
                user={user}
              />
            </header>
            <dl>
              <div>
                <dt>Роль</dt>
                <dd>{user.role === "ADMIN" ? "Администратор" : "Сотрудник"}</dd>
              </div>
              <div>
                <dt>Статус</dt>
                <dd>
                  <StatusBadge active={user.is_active} />
                </dd>
              </div>
              <div>
                <dt>Пароль</dt>
                <dd>
                  {user.must_change_password ? "Нужно сменить" : "Постоянный"}
                </dd>
              </div>
            </dl>
          </article>
        ))}
      </div>
    </>
  );
}

function UserActions({
  user,
  disabled,
  onEdit,
  onReset,
  onDeactivate,
  onActivate,
}: Readonly<{
  user: UserProfile;
  disabled: boolean;
  onEdit: () => void;
  onReset: () => void;
  onDeactivate: () => void;
  onActivate: () => void;
}>) {
  return (
    <details className="action-menu">
      <summary aria-label={`Действия для ${user.full_name}`}>
        <MoreHorizontal size={20} />
      </summary>
      <div className="action-menu-popover">
        <button disabled={disabled} onClick={onEdit} type="button">
          <Edit3 size={16} /> Изменить
        </button>
        <button disabled={disabled} onClick={onReset} type="button">
          <KeyRound size={16} /> Сбросить пароль
        </button>
        <button
          className={user.is_active ? "danger-text" : ""}
          disabled={disabled}
          onClick={user.is_active ? onDeactivate : onActivate}
          type="button"
        >
          <Power size={16} />
          {user.is_active ? "Деактивировать" : "Активировать"}
        </button>
      </div>
    </details>
  );
}

function UserFormDialog({
  mode,
  open,
  user,
  pending = false,
  onClose,
  onCreate,
  onUpdate,
}: Readonly<{
  mode: "create" | "edit";
  open: boolean;
  user?: UserProfile;
  pending?: boolean;
  onClose: () => void;
  onCreate?: (payload: {
    email: string;
    full_name: string;
    role: Role;
  }) => Promise<void>;
  onUpdate?: (
    payload: Pick<UserProfile, "full_name" | "role">,
  ) => Promise<void>;
}>) {
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    setSubmitting(true);
    setFormError(null);
    try {
      if (mode === "create") {
        await onCreate?.({
          email: String(values.get("email") ?? ""),
          full_name: String(values.get("full_name") ?? ""),
          role: String(values.get("role")) as Role,
        });
      } else {
        await onUpdate?.({
          full_name: String(values.get("full_name") ?? ""),
          role: String(values.get("role")) as Role,
        });
      }
    } catch (reason) {
      setFormError(
        reason instanceof Error
          ? reason.message
          : "Не удалось сохранить данные.",
      );
    } finally {
      setSubmitting(false);
    }
  };
  const busy = pending || submitting;
  return (
    <Dialog
      description={
        mode === "create"
          ? "Пользователь получит временный пароль для первого входа."
          : "Измените имя или уровень доступа сотрудника."
      }
      onClose={onClose}
      open={open}
      title={mode === "create" ? "Новый сотрудник" : "Изменить сотрудника"}
    >
      <form className="form-stack" id={`${mode}-user-form`} onSubmit={submit}>
        <FormField htmlFor={`${mode}-name`} label="Полное имя">
          <div className="input-with-icon">
            <UserRound size={17} aria-hidden="true" />
            <input
              autoComplete="name"
              defaultValue={user?.full_name}
              disabled={busy}
              id={`${mode}-name`}
              name="full_name"
              placeholder="Имя Фамилия"
              required
            />
          </div>
        </FormField>
        {mode === "create" && (
          <FormField htmlFor="create-email" label="Email">
            <input
              autoComplete="email"
              disabled={busy}
              id="create-email"
              name="email"
              placeholder="name@company.ru"
              required
              type="email"
            />
          </FormField>
        )}
        <FormField htmlFor={`${mode}-role`} label="Роль">
          <select
            defaultValue={user?.role ?? "EMPLOYEE"}
            disabled={busy}
            id={`${mode}-role`}
            name="role"
          >
            <option value="EMPLOYEE">Сотрудник</option>
            <option value="ADMIN">Администратор</option>
          </select>
        </FormField>
        {formError && (
          <p className="form-error" role="alert">
            {formError}
          </p>
        )}
        <div className="dialog-inline-actions">
          <Button
            disabled={busy}
            onClick={onClose}
            type="button"
            variant="secondary"
          >
            Отмена
          </Button>
          <Button disabled={busy} type="submit">
            {busy
              ? "Сохраняем…"
              : mode === "create"
                ? "Добавить сотрудника"
                : "Сохранить изменения"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
