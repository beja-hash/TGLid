"use client";

import { CheckCircle2, LockKeyhole, ShieldCheck } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";

import { LoginForm } from "../../components/auth/login-form";
import { LoadingState } from "../../components/ui/primitives";
import { useAuth } from "../../src/lib/auth/context";

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <main className="public-shell">
          <LoadingState label="Подготавливаем форму входа" />
        </main>
      }
    >
      <LoginContent />
    </Suspense>
  );
}

function LoginContent() {
  const { state, user } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  useEffect(() => {
    if (state === "authenticated")
      router.replace(user?.must_change_password ? "/change-password" : "/");
  }, [router, state, user]);
  const next = params.get("next");
  const target = next?.startsWith("/") && !next.startsWith("//") ? next : "/";

  if (state === "loading" || state === "authenticated")
    return (
      <main className="public-shell">
        <LoadingState label="Проверяем защищённую сессию" />
      </main>
    );

  return (
    <main className="public-shell">
      <div className="auth-layout">
        <section className="auth-intro" aria-label="О системе">
          <div className="auth-brand">
            <span className="brand-mark">TG</span>
            TGLid
          </div>
          <div>
            <p className="eyebrow light">Внутренняя рабочая система</p>
            <h1>Единое пространство для ежедневной работы команды.</h1>
            <p>
              Безопасный доступ к инструментам управления, сотрудникам и
              системному журналу.
            </p>
          </div>
          <ul className="auth-benefits">
            <li>
              <ShieldCheck size={19} /> Защищённая сессионная авторизация
            </li>
            <li>
              <CheckCircle2 size={19} /> Контроль ролей и действий
            </li>
          </ul>
        </section>
        <section className="auth-card">
          <div className="auth-card-icon" aria-hidden="true">
            <LockKeyhole size={22} />
          </div>
          <p className="eyebrow">Добро пожаловать</p>
          <h2>Вход в TGLid</h2>
          <p className="auth-card-description">
            Используйте корпоративную учётную запись.
          </p>
          {params.get("reason") === "logout" && (
            <p className="notice notice-ok">Вы успешно вышли из системы.</p>
          )}
          <LoginForm onSuccess={() => router.replace(target)} />
          <p className="auth-help">
            Если вы не можете войти, обратитесь к администратору системы.
          </p>
        </section>
      </div>
    </main>
  );
}
