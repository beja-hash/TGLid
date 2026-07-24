"use client";

import {
  Activity,
  Cable,
  CircleOff,
  KeyRound,
  Link2,
  Phone,
  RefreshCw,
  Send,
  ShieldAlert,
  Trash2,
  Unplug,
  UserRound,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { ApiError, api } from "../../src/lib/api/client";
import type {
  TelegramAccount,
  TelegramAccountStatus,
  TelegramAuthChallenge,
} from "../../src/lib/api/types";
import { RequireAdmin } from "../auth/route-guards";
import { Button } from "../ui/button";
import { ConfirmationDialog, Dialog } from "../ui/dialog";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  FormField,
  PageHeader,
  SectionHeader,
  Skeleton,
} from "../ui/primitives";
import { useToast } from "../ui/toast";

type AuthStep = "phone" | "code" | "password";
type LoadState =
  | { kind: "loading" }
  | { kind: "success"; account: TelegramAccount }
  | { kind: "error"; message: string };

const statusPresentation: Record<
  TelegramAccountStatus,
  {
    label: string;
    tone: "neutral" | "accent" | "success" | "warning" | "danger";
    description: string;
  }
> = {
  NOT_CONFIGURED: {
    label: "Не настроен",
    tone: "neutral",
    description: "Telegram credentials не настроены на backend.",
  },
  AUTH_CODE_REQUIRED: {
    label: "Ожидается код",
    tone: "warning",
    description: "Нужно подтвердить вход кодом Telegram.",
  },
  AUTH_PASSWORD_REQUIRED: {
    label: "Требуется 2FA",
    tone: "warning",
    description: "Для аккаунта включён дополнительный пароль.",
  },
  DISCONNECTED: {
    label: "Отключён",
    tone: "neutral",
    description: "Сессия сохранена, постоянное соединение закрыто.",
  },
  CONNECTING: {
    label: "Подключается",
    tone: "accent",
    description: "Backend проверяет сохранённую Telegram-сессию.",
  },
  CONNECTED: {
    label: "Подключён",
    tone: "success",
    description: "Telegram client авторизован и готов к проверкам.",
  },
  ERROR: {
    label: "Ошибка",
    tone: "danger",
    description: "Подключение требует внимания администратора.",
  },
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function friendlyError(reason: unknown): string {
  if (!(reason instanceof ApiError)) {
    return "Не удалось выполнить операцию. Повторите попытку.";
  }
  if (reason.status === 401) return "Сессия TGLid истекла. Войдите снова.";
  if (reason.status === 403)
    return "Недостаточно прав или CSRF-проверка не пройдена.";
  if (reason.status === 410)
    return "Challenge истёк. Начните авторизацию заново.";
  if (reason.status === 429 && reason.retryAfter) {
    return `Telegram ограничил запросы. Повторите через ${reason.retryAfter} сек.`;
  }
  if (reason.status === 429)
    return "Слишком много попыток. Начните авторизацию заново.";
  if (reason.status === 503 && reason.message.includes("Redis")) {
    return "Сервис временного состояния недоступен. Повторите позже.";
  }
  if (reason.status === 503)
    return "Telegram временно недоступен. Повторите позже.";
  if (reason.status === 409)
    return reason.message || "Операция конфликтует с текущим состоянием.";
  if (reason.status === 400)
    return reason.message || "Проверьте введённые данные.";
  return "Не удалось выполнить операцию. Повторите попытку.";
}

export default function TelegramPage() {
  return (
    <RequireAdmin>
      <TelegramContent />
    </RequireAdmin>
  );
}

function TelegramContent() {
  const { notify } = useToast();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [authOpen, setAuthOpen] = useState(false);
  const [authStep, setAuthStep] = useState<AuthStep>("phone");
  const [challenge, setChallenge] = useState<TelegramAuthChallenge | null>(
    null,
  );
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const [authPending, setAuthPending] = useState(false);
  const [actionPending, setActionPending] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const load = useCallback(async (): Promise<void> => {
    setState({ kind: "loading" });
    try {
      setState({ kind: "success", account: await api.telegramAccount() });
    } catch (reason) {
      setState({ kind: "error", message: friendlyError(reason) });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const resetAuthFlow = useCallback(() => {
    setChallenge(null);
    setPhone("");
    setCode("");
    setPassword("");
    setAuthError(null);
    setAuthStep("phone");
    setAuthPending(false);
  }, []);

  const closeAuth = useCallback(() => {
    setAuthOpen(false);
    resetAuthFlow();
  }, [resetAuthFlow]);

  const openAuth = () => {
    resetAuthFlow();
    setAuthOpen(true);
  };

  const expireChallengeWhenNeeded = (reason: unknown) => {
    if (
      reason instanceof ApiError &&
      (reason.status === 410 ||
        (reason.status === 429 && reason.retryAfter === undefined))
    ) {
      setChallenge(null);
      setPhone("");
      setCode("");
      setPassword("");
      setAuthStep("phone");
    }
  };

  const submitAuth = async (
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> => {
    event.preventDefault();
    setAuthError(null);
    setAuthPending(true);
    try {
      if (authStep === "phone") {
        const result = await api.startTelegramAuth(phone);
        setChallenge(result);
        setAuthStep("code");
        return;
      }
      if (!challenge) {
        setAuthStep("phone");
        setAuthError("Challenge недоступен. Начните авторизацию заново.");
        return;
      }
      if (authStep === "code") {
        const submittedCode = code;
        setCode("");
        const result = await api.verifyTelegramCode(
          challenge.challenge_id,
          phone,
          submittedCode,
        );
        if (result.status === "AUTH_PASSWORD_REQUIRED") {
          setChallenge(result);
          setPhone("");
          setAuthStep("password");
          return;
        }
        setPhone("");
        closeAuth();
        notify("Telegram-аккаунт авторизован");
        await load();
        return;
      }
      const submittedPassword = password;
      setPassword("");
      const result = await api.verifyTelegramPassword(
        challenge.challenge_id,
        submittedPassword,
      );
      if (result.status === "DISCONNECTED") {
        closeAuth();
        notify("Telegram-аккаунт авторизован");
        await load();
      }
    } catch (reason) {
      expireChallengeWhenNeeded(reason);
      setAuthError(friendlyError(reason));
    } finally {
      setAuthPending(false);
    }
  };

  const runLifecycle = async (
    action: "connect" | "disconnect" | "check" | "reconnect",
  ): Promise<void> => {
    setActionPending(action);
    setActionError(null);
    try {
      let result: TelegramAccount;
      if (action === "disconnect") result = await api.disconnectTelegram();
      else if (action === "check") result = await api.checkTelegram();
      else if (action === "reconnect") {
        if (state.kind === "success" && state.account.status === "CONNECTED") {
          await api.disconnectTelegram();
        }
        result = await api.connectTelegram();
      } else result = await api.connectTelegram();
      setState({ kind: "success", account: result });
      notify(
        action === "check"
          ? "Соединение проверено"
          : action === "disconnect"
            ? "Telegram отключён"
            : action === "reconnect"
              ? "Telegram переподключён"
              : "Telegram подключён",
      );
    } catch (reason) {
      const message = friendlyError(reason);
      setActionError(message);
      notify(message, "error");
      await load();
    } finally {
      setActionPending(null);
    }
  };

  const removeSession = async (): Promise<void> => {
    setActionPending("delete");
    try {
      await api.removeTelegramSession();
      setDeleteOpen(false);
      closeAuth();
      notify("Подключение Telegram удалено");
      await load();
    } catch (reason) {
      const message = friendlyError(reason);
      notify(message, "error");
    } finally {
      setActionPending(null);
    }
  };

  return (
    <div className="page-stack telegram-page" aria-live="polite">
      <PageHeader
        eyebrow="Интеграции"
        title="Telegram"
        description="Авторизация и lifecycle единственного рабочего аккаунта."
        actions={
          <Button
            disabled={state.kind === "loading"}
            onClick={() => void load()}
            variant="secondary"
          >
            <RefreshCw size={17} /> Обновить
          </Button>
        }
      />

      {state.kind === "loading" ? (
        <Card>
          <Skeleton lines={6} />
        </Card>
      ) : state.kind === "error" ? (
        <Card>
          <ErrorState description={state.message} onRetry={() => void load()} />
        </Card>
      ) : !state.account.configured ? (
        <NotConfigured />
      ) : !state.account.id || !state.account.is_active ? (
        <Card>
          <EmptyState
            title="Аккаунт не авторизован"
            description="Добавьте один рабочий Telegram-аккаунт. Коды и пароль 2FA не сохраняются в браузере."
            action={
              <Button onClick={openAuth}>
                <KeyRound size={17} /> Авторизовать аккаунт
              </Button>
            }
          />
        </Card>
      ) : (
        <AccountCard
          account={state.account}
          actionError={actionError}
          actionPending={actionPending}
          onAuth={openAuth}
          onDelete={() => setDeleteOpen(true)}
          onLifecycle={runLifecycle}
        />
      )}

      <AuthDialog
        challenge={challenge}
        code={code}
        error={authError}
        onClose={closeAuth}
        onCode={setCode}
        onPassword={setPassword}
        onPhone={setPhone}
        onSubmit={submitAuth}
        open={authOpen}
        password={password}
        pending={authPending}
        phone={phone}
        step={authStep}
      />
      <ConfirmationDialog
        danger
        open={deleteOpen}
        title="Удалить подключение Telegram?"
        description="Зашифрованная session будет удалена, а аккаунт деактивирован. Audit history сохранится."
        confirmLabel="Удалить подключение"
        notice="После удаления потребуется повторная авторизация по номеру, коду и при необходимости паролю 2FA."
        pending={actionPending === "delete"}
        onClose={() => setDeleteOpen(false)}
        onConfirm={() => void removeSession()}
      />
    </div>
  );
}

function NotConfigured() {
  return (
    <Card className="telegram-state-card telegram-not-configured">
      <span className="telegram-state-icon" aria-hidden="true">
        <CircleOff size={24} />
      </span>
      <div>
        <p className="eyebrow">Конфигурация</p>
        <h2>Telegram не настроен</h2>
        <p>
          Добавьте Telegram credentials и ключ шифрования на backend. API и
          общий health продолжают работать.
        </p>
      </div>
      <Badge tone="neutral">NOT_CONFIGURED</Badge>
    </Card>
  );
}

function AccountCard({
  account,
  actionError,
  actionPending,
  onAuth,
  onDelete,
  onLifecycle,
}: Readonly<{
  account: TelegramAccount;
  actionError: string | null;
  actionPending: string | null;
  onAuth: () => void;
  onDelete: () => void;
  onLifecycle: (
    action: "connect" | "disconnect" | "check" | "reconnect",
  ) => Promise<void>;
}>) {
  const presentation = statusPresentation[account.status];
  const busy = actionPending !== null || account.status === "CONNECTING";
  const displayName =
    [account.first_name, account.last_name].filter(Boolean).join(" ") ||
    "Telegram-аккаунт";
  return (
    <Card
      className={`telegram-account-card telegram-status-${account.status.toLowerCase()}`}
    >
      <SectionHeader
        title="Рабочий аккаунт"
        description={presentation.description}
        actions={
          <Badge tone={presentation.tone}>
            <span className="status-dot" />
            {presentation.label}
          </Badge>
        }
      />
      <div className="telegram-account-identity">
        <span aria-hidden="true">
          <Send size={22} />
        </span>
        <div>
          <h3>{displayName}</h3>
          <p>
            {account.username ? `@${account.username}` : "Username не указан"}
          </p>
        </div>
      </div>
      {actionError && (
        <p className="notice notice-error" role="alert">
          {actionError}
        </p>
      )}
      {account.status === "ERROR" && account.last_error_message && (
        <div className="telegram-safe-error">
          <ShieldAlert size={19} />
          <div>
            <strong>{account.last_error_code ?? "CONNECTION_ERROR"}</strong>
            <p>{account.last_error_message}</p>
          </div>
        </div>
      )}
      <dl className="detail-list telegram-details">
        <div>
          <dt>
            <UserRound size={15} /> Telegram user ID
          </dt>
          <dd>{account.telegram_user_id ?? "—"}</dd>
        </div>
        <div>
          <dt>
            <Phone size={15} /> Телефон
          </dt>
          <dd>{account.phone_masked ?? "—"}</dd>
        </div>
        <div>
          <dt>
            <Link2 size={15} /> Подключён
          </dt>
          <dd>{formatDate(account.connected_at)}</dd>
        </div>
        <div>
          <dt>
            <Unplug size={15} /> Отключён
          </dt>
          <dd>{formatDate(account.disconnected_at)}</dd>
        </div>
        <div>
          <dt>
            <Activity size={15} /> Последняя проверка
          </dt>
          <dd>{formatDate(account.last_checked_at)}</dd>
        </div>
      </dl>
      <div className="telegram-actions">
        {account.status === "CONNECTED" ? (
          <>
            <Button
              disabled={busy}
              onClick={() => void onLifecycle("check")}
              variant="secondary"
            >
              <Activity size={17} /> Проверить
            </Button>
            <Button
              disabled={busy}
              onClick={() => void onLifecycle("disconnect")}
              variant="secondary"
            >
              <Unplug size={17} /> Отключить
            </Button>
            <Button
              disabled={busy}
              onClick={() => void onLifecycle("reconnect")}
              variant="secondary"
            >
              <RefreshCw size={17} /> Переподключить
            </Button>
          </>
        ) : account.status === "DISCONNECTED" ? (
          <Button disabled={busy} onClick={() => void onLifecycle("connect")}>
            <Cable size={17} /> Подключить
          </Button>
        ) : account.status === "ERROR" ? (
          <>
            <Button
              disabled={busy}
              onClick={() => void onLifecycle("reconnect")}
            >
              <RefreshCw size={17} /> Переподключить
            </Button>
            <Button disabled={busy} onClick={onAuth} variant="secondary">
              <KeyRound size={17} /> Авторизовать заново
            </Button>
          </>
        ) : (
          <Button disabled={busy} onClick={onAuth}>
            <KeyRound size={17} /> Продолжить авторизацию
          </Button>
        )}
        <Button disabled={busy} onClick={onDelete} variant="danger">
          <Trash2 size={17} /> Удалить подключение
        </Button>
      </div>
    </Card>
  );
}

function AuthDialog({
  challenge,
  code,
  error,
  onClose,
  onCode,
  onPassword,
  onPhone,
  onSubmit,
  open,
  password,
  pending,
  phone,
  step,
}: Readonly<{
  challenge: TelegramAuthChallenge | null;
  code: string;
  error: string | null;
  onClose: () => void;
  onCode: (value: string) => void;
  onPassword: (value: string) => void;
  onPhone: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  open: boolean;
  password: string;
  pending: boolean;
  phone: string;
  step: AuthStep;
}>) {
  const title =
    step === "phone"
      ? "Авторизация Telegram"
      : step === "code"
        ? "Введите код"
        : "Введите пароль 2FA";
  const submitLabel =
    step === "phone"
      ? "Получить код"
      : step === "code"
        ? "Подтвердить код"
        : "Подтвердить 2FA";
  return (
    <Dialog
      open={open}
      title={title}
      description={
        step === "phone"
          ? "Данные используются только для текущего защищённого flow."
          : `Код отправлен на ${challenge?.phone_masked ?? "маскированный номер"}. Challenge действует ограниченное время.`
      }
      onClose={onClose}
      footer={
        <>
          <Button
            disabled={pending}
            onClick={onClose}
            type="button"
            variant="secondary"
          >
            Отмена
          </Button>
          <Button disabled={pending} form="telegram-auth-form" type="submit">
            {pending ? "Проверяем…" : submitLabel}
          </Button>
        </>
      }
    >
      <form
        className="form-stack"
        id="telegram-auth-form"
        onSubmit={(event) => void onSubmit(event)}
      >
        {step === "phone" && (
          <FormField
            htmlFor="telegram-phone"
            label="Номер телефона"
            hint="Международный формат, например +7…"
          >
            <input
              autoComplete="tel"
              autoFocus
              id="telegram-phone"
              inputMode="tel"
              onChange={(event) => onPhone(event.target.value)}
              placeholder="+7 999 000-00-00"
              required
              value={phone}
            />
          </FormField>
        )}
        {step === "code" && (
          <FormField
            htmlFor="telegram-code"
            label="Код Telegram"
            hint="Код не сохраняется и очищается после проверки."
          >
            <input
              autoComplete="one-time-code"
              autoFocus
              id="telegram-code"
              inputMode="numeric"
              maxLength={16}
              onChange={(event) => onCode(event.target.value)}
              required
              value={code}
            />
          </FormField>
        )}
        {step === "password" && (
          <FormField
            htmlFor="telegram-password"
            label="Пароль 2FA"
            hint="Пароль не сохраняется и не отправляется в логи."
          >
            <input
              autoComplete="off"
              autoFocus
              id="telegram-password"
              maxLength={256}
              onChange={(event) => onPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
          </FormField>
        )}
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
      </form>
    </Dialog>
  );
}
