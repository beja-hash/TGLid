"use client";

import { useEffect, useState } from "react";

import { formatStatus, type DependencyStatus, type SystemStatus } from "../src/lib/status";

type LoadState =
  | { kind: "loading" }
  | { kind: "success"; value: SystemStatus }
  | { kind: "partial"; value: SystemStatus }
  | { kind: "error" };

const apiUrl = process.env.NEXT_PUBLIC_API_URL;

function statusKind(value: DependencyStatus): "ok" | "unavailable" {
  return value === "ok" ? "ok" : "unavailable";
}

export default function HomePage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    if (!apiUrl) {
      setState({ kind: "error" });
      return;
    }

    const controller = new AbortController();
    const load = async (): Promise<void> => {
      try {
        const response = await fetch(`${apiUrl}/api/v1/system/status`, {
          signal: controller.signal,
          cache: "no-store"
        });

        if (!response.ok) {
          setState({ kind: "error" });
          return;
        }

        const value = (await response.json()) as SystemStatus;
        const isPartial = value.api !== "ok" || value.postgres !== "ok" || value.redis !== "ok";
        setState(isPartial ? { kind: "partial", value } : { kind: "success", value });
      } catch {
        if (!controller.signal.aborted) {
          setState({ kind: "error" });
        }
      }
    };

    void load();
    return () => controller.abort();
  }, []);

  const details = state.kind === "success" || state.kind === "partial" ? state.value : null;

  return (
    <main className="page-shell">
      <section className="status-panel" aria-live="polite">
        <p className="eyebrow">Внутренняя система</p>
        <h1>TGLid</h1>
        <p className="subtitle">Технический фундамент находится в разработке.</p>

        {state.kind === "loading" && <p className="notice">Проверяем доступность сервисов…</p>}
        {state.kind === "error" && (
          <p className="notice notice-error">
            Не удалось связаться с backend. Проверьте, что сервис запущен, и обновите страницу.
          </p>
        )}
        {state.kind === "partial" && (
          <p className="notice notice-warning">Backend доступен, но часть зависимостей временно недоступна.</p>
        )}
        {state.kind === "success" && <p className="notice notice-ok">Все инфраструктурные проверки пройдены.</p>}

        <dl className="status-grid">
          <StatusItem label="Frontend" value="ok" />
          <StatusItem label="Backend" value={details?.api ?? "checking"} />
          <StatusItem label="PostgreSQL" value={details?.postgres ?? "checking"} />
          <StatusItem label="Redis" value={details?.redis ?? "checking"} />
        </dl>
        {details && <p className="environment">Окружение: {details.environment}</p>}
      </section>
    </main>
  );
}

function StatusItem({ label, value }: { label: string; value: DependencyStatus }) {
  return (
    <div className="status-item">
      <dt>{label}</dt>
      <dd className={`status-${statusKind(value)}`}>{formatStatus(value)}</dd>
    </div>
  );
}
