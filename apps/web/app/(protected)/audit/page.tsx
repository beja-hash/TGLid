"use client";

import {
  CalendarDays,
  ChevronRight,
  Filter,
  LogIn,
  MoreHorizontal,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  UserCog,
} from "lucide-react";
import {
  FormEvent,
  useCallback,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { RequireAdmin } from "../../../components/auth/route-guards";
import { Button } from "../../../components/ui/button";
import { Dialog } from "../../../components/ui/dialog";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  FormField,
  PageHeader,
  Pagination,
  Skeleton,
} from "../../../components/ui/primitives";
import { ApiError, api } from "../../../src/lib/api/client";
import type { AuditLog } from "../../../src/lib/api/types";

const pageSize = 50;
const eventDefinitions: Record<
  string,
  {
    label: string;
    category: "authentication" | "users" | "security" | "warning" | "error";
  }
> = {
  AUTH_LOGIN_SUCCEEDED: {
    label: "Успешный вход",
    category: "authentication",
  },
  AUTH_LOGIN_FAILED: {
    label: "Неудачная попытка входа",
    category: "error",
  },
  AUTH_LOGOUT: { label: "Выход из системы", category: "authentication" },
  AUTH_PASSWORD_CHANGED: {
    label: "Пароль изменён",
    category: "security",
  },
  AUTH_RATE_LIMITED: {
    label: "Превышен лимит входа",
    category: "warning",
  },
  USER_CREATED: { label: "Сотрудник создан", category: "users" },
  USER_UPDATED: { label: "Сотрудник изменён", category: "users" },
  USER_ACTIVATED: { label: "Сотрудник активирован", category: "users" },
  USER_DEACTIVATED: {
    label: "Сотрудник деактивирован",
    category: "warning",
  },
  USER_ROLE_CHANGED: {
    label: "Роль сотрудника изменена",
    category: "security",
  },
  USER_PASSWORD_RESET: {
    label: "Пароль сотрудника сброшен",
    category: "security",
  },
  SESSION_REVOKED: { label: "Сессия завершена", category: "security" },
};

const eventOptions = Object.entries(eventDefinitions).sort(([, a], [, b]) =>
  a.label.localeCompare(b.label, "ru"),
);

type Filters = { eventType: string; actor: string; from: string; to: string };
const emptyFilters: Filters = { eventType: "", actor: "", from: "", to: "" };

function shortId(value: string | null): string {
  if (!value) return "Система";
  return value.length > 13 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value;
}

function formatTime(value: string): string {
  return new Date(value).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function eventDefinition(eventType: string) {
  return (
    eventDefinitions[eventType] ?? {
      label: eventType,
      category: "warning" as const,
    }
  );
}

function eventTone(
  category: string,
): "accent" | "success" | "warning" | "danger" {
  if (category === "authentication") return "success";
  if (category === "users") return "accent";
  if (category === "error") return "danger";
  return "warning";
}

function EventIcon({ category }: Readonly<{ category: string }>) {
  const icon: Record<string, ReactNode> = {
    authentication: <LogIn size={18} />,
    users: <UserCog size={18} />,
    security: <ShieldCheck size={18} />,
    warning: <ShieldAlert size={18} />,
    error: <ShieldAlert size={18} />,
  };
  return (
    <span className={`event-icon event-${category}`}>{icon[category]}</span>
  );
}

export default function AuditPage() {
  return (
    <RequireAdmin>
      <AuditContent />
    </RequireAdmin>
  );
}

function AuditContent() {
  const [items, setItems] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [draftFilters, setDraftFilters] = useState<Filters>(emptyFilters);
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [selected, setSelected] = useState<AuditLog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    const query = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    });
    if (filters.eventType) query.set("event_type", filters.eventType);
    if (filters.actor) query.set("actor_user_id", filters.actor.trim());
    if (filters.from)
      query.set("date_from", new Date(filters.from).toISOString());
    if (filters.to) query.set("date_to", new Date(filters.to).toISOString());
    try {
      const result = await api.auditLogs(query);
      setItems(result.items);
      setTotal(result.total);
    } catch (reason) {
      setError(
        reason instanceof ApiError && reason.status === 503
          ? "Журнал аудита временно недоступен."
          : "Не удалось загрузить события. Повторите попытку.",
      );
    } finally {
      setLoading(false);
    }
  }, [filters, page]);

  useEffect(() => {
    void load();
  }, [load]);

  const applyFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPage(1);
    setFilters(draftFilters);
  };
  const clearFilters = () => {
    setDraftFilters(emptyFilters);
    setFilters(emptyFilters);
    setPage(1);
  };
  const hasFilters = Boolean(
    filters.eventType || filters.actor || filters.from || filters.to,
  );

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Безопасность и контроль"
        title="Аудит"
        description={`${total} ${total === 1 ? "событие" : "событий"} в журнале системы`}
      />

      <Card className="filters-card">
        <form className="filter-bar audit-filters" onSubmit={applyFilters}>
          <FormField htmlFor="audit-event" label="Событие">
            <select
              id="audit-event"
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  eventType: event.target.value,
                }))
              }
              value={draftFilters.eventType}
            >
              <option value="">Все события</option>
              {eventOptions.map(([value, definition]) => (
                <option key={value} value={value}>
                  {definition.label}
                </option>
              ))}
            </select>
          </FormField>
          <FormField htmlFor="audit-actor" label="Инициатор">
            <input
              id="audit-actor"
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  actor: event.target.value,
                }))
              }
              placeholder="UUID пользователя"
              value={draftFilters.actor}
            />
          </FormField>
          <FormField htmlFor="audit-from" label="Дата от">
            <input
              id="audit-from"
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  from: event.target.value,
                }))
              }
              type="datetime-local"
              value={draftFilters.from}
            />
          </FormField>
          <FormField htmlFor="audit-to" label="Дата до">
            <input
              id="audit-to"
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  to: event.target.value,
                }))
              }
              type="datetime-local"
              value={draftFilters.to}
            />
          </FormField>
          <div className="filter-actions">
            <Button type="submit" variant="secondary">
              <Filter size={16} /> Применить
            </Button>
            <Button
              disabled={!hasFilters}
              onClick={clearFilters}
              type="button"
              variant="ghost"
            >
              <RotateCcw size={16} /> Очистить
            </Button>
          </div>
        </form>
      </Card>

      <Card className="data-card">
        {loading ? (
          <Skeleton lines={7} compact />
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
                ? "Измените условия поиска или очистите фильтры."
                : "Здесь появятся значимые действия пользователей."
            }
            title={hasFilters ? "События не найдены" : "Журнал пока пуст"}
          />
        ) : (
          <AuditList items={items} onDetails={setSelected} />
        )}
        <Pagination
          onPage={setPage}
          page={page}
          pageSize={pageSize}
          total={total}
        />
      </Card>

      <AuditDetails item={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

function AuditList({
  items,
  onDetails,
}: Readonly<{
  items: AuditLog[];
  onDetails: (item: AuditLog) => void;
}>) {
  return (
    <>
      <div className="desktop-table">
        <table>
          <thead>
            <tr>
              <th>Дата и время</th>
              <th>Событие</th>
              <th>Инициатор</th>
              <th>Объект</th>
              <th>IP-адрес</th>
              <th>
                <span className="visually-hidden">Подробнее</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const definition = eventDefinition(item.event_type);
              return (
                <tr key={item.id}>
                  <td className="date-cell">{formatTime(item.created_at)}</td>
                  <td>
                    <div className="event-cell">
                      <EventIcon category={definition.category} />
                      <div>
                        <strong>{definition.label}</strong>
                        <Badge tone={eventTone(definition.category)}>
                          {definition.category === "users"
                            ? "Сотрудники"
                            : definition.category === "authentication"
                              ? "Авторизация"
                              : definition.category === "error"
                                ? "Ошибка"
                                : "Безопасность"}
                        </Badge>
                      </div>
                    </div>
                  </td>
                  <td title={item.actor_user_id ?? "Система"}>
                    {shortId(item.actor_user_id)}
                  </td>
                  <td title={item.target_id ?? undefined}>
                    <span className="target-type">{item.target_type}</span>
                    {item.target_id ? ` · ${shortId(item.target_id)}` : ""}
                  </td>
                  <td>{item.ip_address ?? "—"}</td>
                  <td>
                    <button
                      className="details-button"
                      onClick={() => onDetails(item)}
                      type="button"
                    >
                      Подробнее <ChevronRight size={16} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="mobile-cards audit-mobile-list">
        {items.map((item) => {
          const definition = eventDefinition(item.event_type);
          return (
            <button
              className="mobile-data-card audit-mobile-card"
              key={item.id}
              onClick={() => onDetails(item)}
              type="button"
            >
              <span className="event-mobile-heading">
                <EventIcon category={definition.category} />
                <span>
                  <strong>{definition.label}</strong>
                  <small>{formatTime(item.created_at)}</small>
                </span>
                <MoreHorizontal size={19} />
              </span>
              <span className="audit-mobile-meta">
                <span>Инициатор: {shortId(item.actor_user_id)}</span>
                <span>IP: {item.ip_address ?? "—"}</span>
              </span>
            </button>
          );
        })}
      </div>
    </>
  );
}

function AuditDetails({
  item,
  onClose,
}: Readonly<{ item: AuditLog | null; onClose: () => void }>) {
  const definition = item ? eventDefinition(item.event_type) : null;
  return (
    <Dialog
      description={item ? formatTime(item.created_at) : undefined}
      onClose={onClose}
      open={Boolean(item)}
      size="wide"
      title={definition?.label ?? "Подробности события"}
    >
      {item && definition && (
        <div className="audit-details">
          <div className="audit-detail-summary">
            <EventIcon category={definition.category} />
            <div>
              <strong>{definition.label}</strong>
              <code>{item.event_type}</code>
            </div>
            <Badge tone={eventTone(definition.category)}>
              {definition.category}
            </Badge>
          </div>
          <dl className="detail-list compact">
            <div>
              <dt>
                <CalendarDays size={16} /> Полное время
              </dt>
              <dd>{formatTime(item.created_at)}</dd>
            </div>
            <div>
              <dt>Инициатор</dt>
              <dd className="breakable">{item.actor_user_id ?? "Система"}</dd>
            </div>
            <div>
              <dt>Тип объекта</dt>
              <dd>{item.target_type}</dd>
            </div>
            <div>
              <dt>Идентификатор объекта</dt>
              <dd className="breakable">{item.target_id ?? "—"}</dd>
            </div>
            <div>
              <dt>IP-адрес</dt>
              <dd>{item.ip_address ?? "—"}</dd>
            </div>
            <div>
              <dt>User-Agent</dt>
              <dd className="breakable">{item.user_agent ?? "—"}</dd>
            </div>
          </dl>
          <section className="metadata-section">
            <h3>Дополнительные данные</h3>
            {Object.keys(item.metadata).length === 0 ? (
              <p className="muted-copy">Дополнительных данных нет.</p>
            ) : (
              <dl className="metadata-list">
                {Object.entries(item.metadata).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key}</dt>
                    <dd>{formatMetadataValue(value)}</dd>
                  </div>
                ))}
              </dl>
            )}
          </section>
          <p className="technical-id">ID события: {item.id}</p>
        </div>
      )}
    </Dialog>
  );
}

function formatMetadataValue(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean")
    return String(value);
  return JSON.stringify(value);
}
