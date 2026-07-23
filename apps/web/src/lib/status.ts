export type DependencyStatus = "ok" | "unavailable" | "checking";

export type SystemStatus = {
  api: DependencyStatus;
  postgres: DependencyStatus;
  redis: DependencyStatus;
  environment: string;
};

export function formatStatus(status: DependencyStatus): string {
  const labels: Record<DependencyStatus, string> = {
    ok: "Доступен",
    unavailable: "Недоступен",
    checking: "Проверяется"
  };
  return labels[status];
}
