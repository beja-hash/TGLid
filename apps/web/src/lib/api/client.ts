import type {
  AuditLog,
  Paginated,
  SystemStatus,
  TelegramAccount,
  TelegramAuthChallenge,
  UserProfile,
  UserWithTemporaryPassword,
} from "./types";

type ApiErrorBody = {
  error?: { code?: string; message?: string; request_id?: string };
};
type RequestOptions = Omit<RequestInit, "body" | "method"> & {
  body?: unknown;
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
};

const unsafeMethods = new Set(["POST", "PATCH", "PUT", "DELETE"]);
const apiUrl = process.env.NEXT_PUBLIC_API_URL;
const csrfCookieName = process.env.NEXT_PUBLIC_CSRF_COOKIE_NAME ?? "tglid_csrf";
const csrfHeaderName =
  process.env.NEXT_PUBLIC_CSRF_HEADER_NAME ?? "X-CSRF-Token";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly retryAfter?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

let onUnauthorized: (() => void) | undefined;

export function setUnauthorizedHandler(
  handler: (() => void) | undefined,
): void {
  onUnauthorized = handler;
}

export function readCsrfToken(
  cookie = typeof document === "undefined" ? "" : document.cookie,
): string | undefined {
  const prefix = `${csrfCookieName}=`;
  const item = cookie.split("; ").find((entry) => entry.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : undefined;
}

function buildUrl(path: string, query?: URLSearchParams): string {
  if (!apiUrl) {
    throw new ApiError(
      503,
      "CONFIGURATION_ERROR",
      "Frontend не настроен для связи с backend",
    );
  }
  const suffix = query && query.size > 0 ? `?${query.toString()}` : "";
  return `${apiUrl}${path}${suffix}`;
}

async function parseError(response: Response): Promise<ApiError> {
  let payload: ApiErrorBody | undefined;
  try {
    payload = (await response.json()) as ApiErrorBody;
  } catch {
    payload = undefined;
  }
  const retryAfterValue = response.headers.get("Retry-After");
  const retryAfter = retryAfterValue
    ? Number.parseInt(retryAfterValue, 10)
    : undefined;
  return new ApiError(
    response.status,
    payload?.error?.code ?? "REQUEST_ERROR",
    payload?.error?.message ?? "Не удалось выполнить запрос",
    Number.isFinite(retryAfter) ? retryAfter : undefined,
  );
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (unsafeMethods.has(method) && path !== "/api/v1/auth/login") {
    const csrfToken = readCsrfToken();
    if (!csrfToken) {
      throw new ApiError(
        403,
        "CSRF_MISSING",
        "Не удалось подтвердить безопасность запроса. Обновите страницу.",
      );
    }
    headers.set(csrfHeaderName, csrfToken);
  }

  const response = await fetch(buildUrl(path), {
    ...options,
    method,
    headers,
    credentials: "include",
    cache: "no-store",
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  if (!response.ok) {
    const error = await parseError(response);
    if (error.status === 401) {
      onUnauthorized?.();
    }
    throw error;
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  login: (email: string, password: string): Promise<UserProfile> =>
    apiRequest("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
    }),
  me: (): Promise<UserProfile> => apiRequest("/api/v1/auth/me"),
  logout: (): Promise<void> =>
    apiRequest("/api/v1/auth/logout", { method: "POST" }),
  changePassword: (
    currentPassword: string,
    newPassword: string,
  ): Promise<UserProfile> =>
    apiRequest("/api/v1/auth/change-password", {
      method: "POST",
      body: { current_password: currentPassword, new_password: newPassword },
    }),
  systemStatus: (): Promise<SystemStatus> =>
    apiRequest("/api/v1/system/status"),
  users: (query: URLSearchParams): Promise<Paginated<UserProfile>> =>
    apiRequest(`/api/v1/users${query.size > 0 ? `?${query.toString()}` : ""}`),
  createUser: (payload: {
    email: string;
    full_name: string;
    role: "ADMIN" | "EMPLOYEE";
  }): Promise<UserWithTemporaryPassword> =>
    apiRequest("/api/v1/users", { method: "POST", body: payload }),
  updateUser: (
    id: string,
    payload: Partial<Pick<UserProfile, "full_name" | "role" | "is_active">>,
  ): Promise<UserProfile> =>
    apiRequest(`/api/v1/users/${id}`, { method: "PATCH", body: payload }),
  resetPassword: (id: string): Promise<UserWithTemporaryPassword> =>
    apiRequest(`/api/v1/users/${id}/reset-password`, { method: "POST" }),
  auditLogs: (query: URLSearchParams): Promise<Paginated<AuditLog>> =>
    apiRequest(
      `/api/v1/audit-logs${query.size > 0 ? `?${query.toString()}` : ""}`,
    ),
  telegramAccount: (): Promise<TelegramAccount> =>
    apiRequest("/api/v1/telegram-account"),
  startTelegramAuth: (phone: string): Promise<TelegramAuthChallenge> =>
    apiRequest("/api/v1/telegram-account/auth/start", {
      method: "POST",
      body: { phone },
    }),
  verifyTelegramCode: (
    challengeId: string,
    phone: string,
    code: string,
  ): Promise<TelegramAuthChallenge> =>
    apiRequest("/api/v1/telegram-account/auth/verify-code", {
      method: "POST",
      body: { challenge_id: challengeId, phone, code },
    }),
  verifyTelegramPassword: (
    challengeId: string,
    password: string,
  ): Promise<TelegramAuthChallenge> =>
    apiRequest("/api/v1/telegram-account/auth/verify-password", {
      method: "POST",
      body: { challenge_id: challengeId, password },
    }),
  connectTelegram: (): Promise<TelegramAccount> =>
    apiRequest("/api/v1/telegram-account/connect", { method: "POST" }),
  disconnectTelegram: (): Promise<TelegramAccount> =>
    apiRequest("/api/v1/telegram-account/disconnect", { method: "POST" }),
  checkTelegram: (): Promise<TelegramAccount> =>
    apiRequest("/api/v1/telegram-account/check", { method: "POST" }),
  removeTelegramSession: (): Promise<void> =>
    apiRequest("/api/v1/telegram-account/session", { method: "DELETE" }),
};
