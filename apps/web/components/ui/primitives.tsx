import type { ReactNode } from "react";
import { AlertCircle, Inbox, LoaderCircle } from "lucide-react";

export function Card({
  children,
  className = "",
}: Readonly<{ children: ReactNode; className?: string }>) {
  return <section className={`card ${className}`.trim()}>{children}</section>;
}

export function Badge({
  children,
  tone = "neutral",
}: Readonly<{
  children: ReactNode;
  tone?: "neutral" | "accent" | "success" | "warning" | "danger";
}>) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function StatusBadge({
  active,
  activeLabel = "Активен",
  inactiveLabel = "Неактивен",
}: Readonly<{
  active: boolean;
  activeLabel?: string;
  inactiveLabel?: string;
}>) {
  return (
    <Badge tone={active ? "success" : "danger"}>
      <span aria-hidden="true" className="status-dot" />
      {active ? activeLabel : inactiveLabel}
    </Badge>
  );
}

export function FormField({
  label,
  htmlFor,
  hint,
  error,
  children,
  className = "",
}: Readonly<{
  label: string;
  htmlFor: string;
  hint?: string;
  error?: string;
  children: ReactNode;
  className?: string;
}>) {
  return (
    <div className={`form-field ${className}`.trim()}>
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && !error && <span className="field-hint">{hint}</span>}
      {error && (
        <span className="field-error" id={`${htmlFor}-error`} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: Readonly<{
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}>) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

export function SectionHeader({
  title,
  description,
  actions,
}: Readonly<{
  title: string;
  description?: string;
  actions?: ReactNode;
}>) {
  return (
    <header className="section-header">
      <div>
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      {actions}
    </header>
  );
}

export function Skeleton({
  lines = 3,
  compact = false,
}: Readonly<{ lines?: number; compact?: boolean }>) {
  return (
    <div
      className={compact ? "skeleton compact" : "skeleton"}
      aria-label="Загрузка"
    >
      {Array.from({ length: lines }, (_, index) => (
        <span key={index} />
      ))}
    </div>
  );
}

export function LoadingState({
  label = "Загрузка данных",
}: {
  label?: string;
}) {
  return (
    <div className="state-block" role="status">
      <LoaderCircle aria-hidden="true" className="spin" size={22} />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: Readonly<{ title: string; description: string; action?: ReactNode }>) {
  return (
    <div className="empty-state">
      <span className="state-icon" aria-hidden="true">
        <Inbox size={22} />
      </span>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}

export function ErrorState({
  title = "Не удалось загрузить данные",
  description,
  onRetry,
}: Readonly<{
  title?: string;
  description: string;
  onRetry?: () => void;
}>) {
  return (
    <div className="error-state" role="alert">
      <span className="state-icon danger" aria-hidden="true">
        <AlertCircle size={22} />
      </span>
      <div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      {onRetry && (
        <button
          className="button button-secondary button-small"
          onClick={onRetry}
          type="button"
        >
          Повторить
        </button>
      )}
    </div>
  );
}

export function Pagination({
  page,
  total,
  pageSize,
  onPage,
}: Readonly<{
  page: number;
  total: number;
  pageSize: number;
  onPage: (page: number) => void;
}>) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <nav className="pagination" aria-label="Пагинация">
      <button
        className="button button-secondary button-small"
        type="button"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
      >
        Назад
      </button>
      <span>
        {page} из {pages}
      </span>
      <button
        className="button button-secondary button-small"
        type="button"
        disabled={page >= pages}
        onClick={() => onPage(page + 1)}
      >
        Вперёд
      </button>
    </nav>
  );
}
