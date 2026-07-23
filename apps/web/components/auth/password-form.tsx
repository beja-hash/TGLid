"use client";

import { Eye, EyeOff, KeyRound, LoaderCircle } from "lucide-react";
import { FormEvent, useState } from "react";

import { ApiError } from "../../src/lib/api/client";
import { Button, IconButton } from "../ui/button";
import { FormField } from "../ui/primitives";

type FieldErrors = {
  current?: string;
  next?: string;
  confirmation?: string;
  form?: string;
};

function PasswordInput({
  id,
  value,
  onChange,
  autoComplete,
  disabled,
  describedBy,
}: Readonly<{
  id: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: string;
  disabled: boolean;
  describedBy?: string;
}>) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="password-input">
      <input
        aria-describedby={describedBy}
        aria-invalid={Boolean(describedBy)}
        autoComplete={autoComplete}
        disabled={disabled}
        id={id}
        onChange={(event) => onChange(event.target.value)}
        required
        type={visible ? "text" : "password"}
        value={value}
      />
      <IconButton
        disabled={disabled}
        label={visible ? "Скрыть пароль" : "Показать пароль"}
        onClick={() => setVisible((current) => !current)}
        type="button"
      >
        {visible ? <EyeOff size={18} /> : <Eye size={18} />}
      </IconButton>
    </div>
  );
}

export function PasswordForm({
  onSubmit,
}: Readonly<{
  onSubmit: (currentPassword: string, newPassword: string) => Promise<void>;
}>) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [success, setSuccess] = useState(false);
  const [pending, setPending] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    setErrors({});
    setSuccess(false);
    const nextErrors: FieldErrors = {};
    if (!currentPassword) nextErrors.current = "Введите текущий пароль.";
    if (newPassword.length < 10)
      nextErrors.next = "Пароль должен содержать не менее 10 символов.";
    if (newPassword.length > 128)
      nextErrors.next = "Пароль не может быть длиннее 128 символов.";
    if (newPassword !== confirmation)
      nextErrors.confirmation = "Подтверждение пароля не совпадает.";
    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors);
      return;
    }
    setPending(true);
    try {
      await onSubmit(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmation("");
      setSuccess(true);
    } catch (reason) {
      setErrors({
        form:
          reason instanceof ApiError
            ? reason.message
            : "Не удалось сменить пароль. Попробуйте ещё раз.",
      });
    } finally {
      setPending(false);
    }
  };

  return (
    <form className="form-stack" onSubmit={(event) => void submit(event)}>
      <FormField
        error={errors.current}
        htmlFor="current-password"
        label="Текущий пароль"
      >
        <PasswordInput
          autoComplete="current-password"
          describedBy={errors.current ? "current-password-error" : undefined}
          disabled={pending}
          id="current-password"
          onChange={setCurrentPassword}
          value={currentPassword}
        />
      </FormField>
      <FormField
        error={errors.next}
        hint="От 10 до 128 символов."
        htmlFor="new-password"
        label="Новый пароль"
      >
        <PasswordInput
          autoComplete="new-password"
          describedBy={errors.next ? "new-password-error" : undefined}
          disabled={pending}
          id="new-password"
          onChange={setNewPassword}
          value={newPassword}
        />
      </FormField>
      <FormField
        error={errors.confirmation}
        htmlFor="confirm-password"
        label="Подтвердите новый пароль"
      >
        <PasswordInput
          autoComplete="new-password"
          describedBy={
            errors.confirmation ? "confirm-password-error" : undefined
          }
          disabled={pending}
          id="confirm-password"
          onChange={setConfirmation}
          value={confirmation}
        />
      </FormField>
      {errors.form && (
        <p className="form-error" role="alert">
          {errors.form}
        </p>
      )}
      {success && (
        <p className="notice notice-ok" role="status">
          Пароль успешно изменён. Перенаправляем на обзор.
        </p>
      )}
      <Button disabled={pending} type="submit">
        {pending ? (
          <>
            <LoaderCircle className="spin" size={18} /> Сохраняем
          </>
        ) : (
          <>
            <KeyRound size={18} /> Сменить пароль
          </>
        )}
      </Button>
    </form>
  );
}
