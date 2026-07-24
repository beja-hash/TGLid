"use client";

import {
  CheckCircle2,
  CloudCog,
  Database,
  Globe2,
  RefreshCw,
  Server,
  Send,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { Button } from "../../components/ui/button";
import {
  Badge,
  Card,
  ErrorState,
  PageHeader,
  Skeleton,
} from "../../components/ui/primitives";
import { ApiError, api } from "../../src/lib/api/client";
import type { SystemStatus } from "../../src/lib/api/types";
import type { TelegramAccount } from "../../src/lib/api/types";
import { useAuth } from "../../src/lib/auth/context";

type LoadState =
  | { kind: "loading" }
  | { kind: "success"; value: SystemStatus; checkedAt: Date }
  | { kind: "error"; message: string };

export default function HomePage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [refreshing, setRefreshing] = useState(false);
  const [telegram, setTelegram] = useState<TelegramAccount | null>(null);
  const { user } = useAuth();

  const load = useCallback(async (isRefresh = false): Promise<void> => {
    if (isRefresh) setRefreshing(true);
    else setState({ kind: "loading" });
    try {
      const value = await api.systemStatus();
      setState({ kind: "success", value, checkedAt: new Date() });
    } catch (reason) {
      setState({
        kind: "error",
        message:
          reason instanceof ApiError && reason.status === 403
            ? "Для просмотра статуса недостаточно прав."
            : "Не удалось получить состояние сервисов. Backend может быть временно недоступен.",
      });
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (user?.role !== "ADMIN") return;
    void api
      .telegramAccount()
      .then(setTelegram)
      .catch(() => setTelegram(null));
  }, [user?.role]);

  const details = state.kind === "success" ? state.value : undefined;
  const allAvailable =
    details?.api === "ok" &&
    details.postgres === "ok" &&
    details.redis === "ok";

  return (
    <div className="page-stack" aria-live="polite">
      <PageHeader
        eyebrow="Рабочая область"
        title={`Добрый день, ${user?.full_name?.split(" ")[0] ?? "коллега"}`}
        description="Текущее состояние инфраструктуры TGLid."
        actions={
          <Button
            disabled={refreshing || state.kind === "loading"}
            onClick={() => void load(true)}
            variant="secondary"
          >
            <RefreshCw className={refreshing ? "spin" : undefined} size={17} />
            Проверить снова
          </Button>
        }
      />

      {state.kind === "loading" ? (
        <Card>
          <Skeleton lines={4} />
        </Card>
      ) : state.kind === "error" ? (
        <Card>
          <ErrorState description={state.message} onRetry={() => void load()} />
        </Card>
      ) : (
        <>
          <Card
            className={
              allAvailable ? "health-summary ok" : "health-summary warning"
            }
          >
            <span className="health-summary-icon" aria-hidden="true">
              {allAvailable ? (
                <CheckCircle2 size={25} />
              ) : (
                <TriangleAlert size={25} />
              )}
            </span>
            <div>
              <p className="eyebrow">Общий статус</p>
              <h2>
                {allAvailable
                  ? "Все системы работают штатно"
                  : "Часть сервисов недоступна"}
              </h2>
              <p>
                {allAvailable
                  ? "Инфраструктура готова к работе."
                  : "Проверьте отдельные сервисы ниже и повторите диагностику."}
              </p>
            </div>
            <Badge tone={allAvailable ? "success" : "warning"}>
              {allAvailable ? "Работает" : "Требует внимания"}
            </Badge>
          </Card>

          <div className="service-grid">
            <ServiceCard
              description="Пользовательский интерфейс"
              icon={<Globe2 size={21} />}
              name="Frontend"
              status="ok"
            />
            <ServiceCard
              description="Сервер приложений и API"
              icon={<Server size={21} />}
              name="API"
              status={state.value.api}
            />
            <ServiceCard
              description="Основное хранилище данных"
              icon={<Database size={21} />}
              name="PostgreSQL"
              status={state.value.postgres}
            />
            <ServiceCard
              description="Сессии и ограничение запросов"
              icon={<CloudCog size={21} />}
              name="Redis"
              status={state.value.redis}
            />
          </div>

          {user?.role === "ADMIN" && (
            <Card className="dashboard-telegram-card">
              <span className="service-icon" aria-hidden="true">
                <Send size={20} />
              </span>
              <div>
                <h3>Telegram</h3>
                <p>
                  {telegram
                    ? telegram.configured
                      ? `Статус аккаунта: ${telegram.status}`
                      : "Интеграция не настроена"
                    : "Статус временно недоступен"}
                </p>
              </div>
              <Badge
                tone={
                  telegram?.status === "CONNECTED"
                    ? "success"
                    : telegram?.status === "ERROR"
                      ? "danger"
                      : "neutral"
                }
              >
                {telegram?.status === "CONNECTED"
                  ? "Подключён"
                  : telegram?.status === "ERROR"
                    ? "Ошибка"
                    : "Не влияет на health"}
              </Badge>
              <Link
                className="button button-secondary button-small"
                href="/telegram"
              >
                Управление
              </Link>
            </Card>
          )}

          <div className="status-meta">
            <span>
              Окружение: <strong>{state.value.environment}</strong>
            </span>
            <span>
              Последняя проверка:{" "}
              <strong>
                {state.checkedAt.toLocaleTimeString("ru-RU", {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                })}
              </strong>
            </span>
          </div>
        </>
      )}
    </div>
  );
}

function ServiceCard({
  name,
  description,
  status,
  icon,
}: Readonly<{
  name: string;
  description: string;
  status: "ok" | "unavailable";
  icon: ReactNode;
}>) {
  const available = status === "ok";
  return (
    <Card className="service-card">
      <span className="service-icon" aria-hidden="true">
        {icon}
      </span>
      <div className="service-copy">
        <h3>{name}</h3>
        <p>{description}</p>
      </div>
      <Badge tone={available ? "success" : "danger"}>
        <span className="status-dot" aria-hidden="true" />
        {available ? "Доступен" : "Недоступен"}
      </Badge>
    </Card>
  );
}
