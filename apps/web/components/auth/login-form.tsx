"use client";

import { ArrowRight, LoaderCircle } from "lucide-react";
import { FormEvent, useState } from "react";

import { ApiError } from "../../src/lib/api/client";
import { useAuth } from "../../src/lib/auth/context";
import { Button } from "../ui/button";
import { FormField } from "../ui/primitives";

export function LoginForm({ onSuccess }: Readonly<{ onSuccess: () => void }>) {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      await login(email, password);
      setPassword("");
      onSuccess();
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401)
        setError("Неверный email или пароль");
      else if (reason instanceof ApiError && reason.status === 429)
        setError(
          `Слишком много попыток. Повторите через ${reason.retryAfter ?? "несколько"} секунд.`,
        );
      else if (reason instanceof ApiError && reason.status === 503)
        setError("Вход временно недоступен. Попробуйте позже.");
      else setError("Не удалось выполнить вход. Попробуйте ещё раз.");
    } finally {
      setPending(false);
    }
  };

  return (
    <form
      className="form-stack auth-form"
      onSubmit={(event) => void submit(event)}
    >
      <FormField htmlFor="email" label="Email">
        <input
          autoComplete="email"
          disabled={pending}
          id="email"
          inputMode="email"
          name="email"
          onChange={(event) => setEmail(event.target.value)}
          placeholder="name@company.ru"
          required
          type="email"
          value={email}
        />
      </FormField>
      <FormField htmlFor="password" label="Пароль">
        <input
          autoComplete="current-password"
          disabled={pending}
          id="password"
          name="password"
          onChange={(event) => setPassword(event.target.value)}
          placeholder="Введите пароль"
          required
          type="password"
          value={password}
        />
      </FormField>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <Button className="button-wide" disabled={pending} type="submit">
        {pending ? (
          <>
            <LoaderCircle className="spin" size={18} /> Выполняем вход
          </>
        ) : (
          <>
            Войти <ArrowRight size={18} />
          </>
        )}
      </Button>
    </form>
  );
}
