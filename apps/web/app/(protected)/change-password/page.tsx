"use client";

import { ShieldAlert, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";

import { PasswordForm } from "../../../components/auth/password-form";
import { Card, PageHeader } from "../../../components/ui/primitives";
import { api } from "../../../src/lib/api/client";
import { useAuth } from "../../../src/lib/auth/context";

export default function ChangePasswordPage() {
  const { user, setUser, refreshProfile } = useAuth();
  const router = useRouter();
  const submit = async (
    currentPassword: string,
    newPassword: string,
  ): Promise<void> => {
    const profile = await api.changePassword(currentPassword, newPassword);
    setUser(profile);
    await refreshProfile();
    window.setTimeout(() => router.replace("/"), 900);
  };

  return (
    <div className="page-stack narrow-page">
      <PageHeader
        eyebrow="Безопасность"
        title="Смена пароля"
        description="Используйте пароль, который вы не применяете в других сервисах."
      />
      {user?.must_change_password && (
        <div className="mandatory-password" role="alert">
          <ShieldAlert size={22} aria-hidden="true" />
          <div>
            <strong>Необходимо заменить временный пароль</strong>
            <p>До смены пароля другие разделы системы будут недоступны.</p>
          </div>
        </div>
      )}
      <Card className="password-card">
        <div className="password-card-heading">
          <span aria-hidden="true">
            <ShieldCheck size={22} />
          </span>
          <div>
            <h2>Новый пароль</h2>
            <p>Допустимая длина — от 10 до 128 символов.</p>
          </div>
        </div>
        <PasswordForm onSubmit={submit} />
      </Card>
    </div>
  );
}
