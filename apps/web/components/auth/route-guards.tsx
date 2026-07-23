"use client";

import { ShieldX } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "../../src/lib/auth/context";
import { ErrorState, LoadingState } from "../ui/primitives";

export function RequireAuth({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const { state, user } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (state === "anonymous") {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
    if (
      state === "authenticated" &&
      user?.must_change_password &&
      pathname !== "/change-password"
    ) {
      router.replace("/change-password");
    }
  }, [pathname, router, state, user]);

  if (state === "loading")
    return (
      <main className="fullscreen-state">
        <LoadingState label="Проверяем защищённую сессию" />
      </main>
    );
  if (state === "unavailable")
    return (
      <main className="fullscreen-state">
        <ErrorState
          title="Сервис временно недоступен"
          description="Не удалось связаться с backend. Проверьте подключение и повторите попытку."
          onRetry={() => window.location.reload()}
        />
      </main>
    );
  if (!user || (user.must_change_password && pathname !== "/change-password"))
    return (
      <main className="fullscreen-state">
        <LoadingState label="Перенаправляем" />
      </main>
    );
  return <>{children}</>;
}

export function RequireAdmin({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const { user } = useAuth();
  if (user?.role !== "ADMIN") {
    return (
      <section className="forbidden-state">
        <span className="state-icon danger" aria-hidden="true">
          <ShieldX size={24} />
        </span>
        <p className="eyebrow">Доступ ограничен</p>
        <h1>Недостаточно прав</h1>
        <p>Этот раздел доступен только администраторам TGLid.</p>
      </section>
    );
  }
  return <>{children}</>;
}
