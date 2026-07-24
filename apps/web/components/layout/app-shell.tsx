"use client";

import {
  ClipboardList,
  LayoutDashboard,
  LogOut,
  Menu,
  ShieldCheck,
  Send,
  UserRound,
  UsersRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { useAuth } from "../../src/lib/auth/context";
import { Badge } from "../ui/primitives";

function NavLink({
  href,
  icon,
  children,
  onClick,
}: Readonly<{
  href: string;
  icon: ReactNode;
  children: ReactNode;
  onClick?: () => void;
}>) {
  const pathname = usePathname();
  const active = pathname === href;
  return (
    <Link
      aria-current={active ? "page" : undefined}
      className={active ? "nav-link active" : "nav-link"}
      href={href}
      onClick={onClick}
    >
      {icon}
      {children}
    </Link>
  );
}

const pageTitles: Record<string, { title: string; description: string }> = {
  "/": {
    title: "Обзор",
    description: "Состояние сервисов и готовность системы",
  },
  "/profile": {
    title: "Профиль",
    description: "Учётная запись и безопасность",
  },
  "/change-password": {
    title: "Смена пароля",
    description: "Обновление данных для входа",
  },
  "/users": {
    title: "Сотрудники",
    description: "Доступы и роли команды",
  },
  "/audit": {
    title: "Аудит",
    description: "Журнал действий в системе",
  },
  "/telegram": {
    title: "Telegram",
    description: "Авторизация и состояние подключения",
  },
};

export function AppShell({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => setMenuOpen(false), [pathname]);
  useEffect(() => {
    document.body.classList.toggle("sidebar-open", menuOpen);
    return () => document.body.classList.remove("sidebar-open");
  }, [menuOpen]);

  const handleLogout = async (): Promise<void> => {
    setIsLoggingOut(true);
    await logout();
    window.location.assign("/login?reason=logout");
  };
  const currentPage = pageTitles[pathname] ?? pageTitles["/"];
  const closeMenu = () => setMenuOpen(false);

  return (
    <div className="app-shell">
      <aside className={menuOpen ? "sidebar open" : "sidebar"}>
        <div className="sidebar-brand">
          <Link className="brand" href="/" onClick={closeMenu}>
            <span className="brand-mark" aria-hidden="true">
              TG
            </span>
            <span>
              TGLid
              <small>Workspace</small>
            </span>
          </Link>
          <button
            aria-label="Закрыть меню"
            className="sidebar-close"
            onClick={closeMenu}
            type="button"
          >
            <X size={20} />
          </button>
        </div>
        <nav aria-label="Основная навигация" className="sidebar-nav">
          <p className="nav-label">Рабочая область</p>
          <NavLink
            href="/"
            icon={<LayoutDashboard size={19} />}
            onClick={closeMenu}
          >
            Обзор
          </NavLink>
          <NavLink
            href="/profile"
            icon={<UserRound size={19} />}
            onClick={closeMenu}
          >
            Профиль
          </NavLink>
          {user?.role === "ADMIN" && (
            <>
              <p className="nav-label nav-label-spaced">Управление</p>
              <NavLink
                href="/users"
                icon={<UsersRound size={19} />}
                onClick={closeMenu}
              >
                Сотрудники
              </NavLink>
              <NavLink
                href="/telegram"
                icon={<Send size={19} />}
                onClick={closeMenu}
              >
                Telegram
              </NavLink>
              <NavLink
                href="/audit"
                icon={<ClipboardList size={19} />}
                onClick={closeMenu}
              >
                Аудит
              </NavLink>
            </>
          )}
        </nav>
        <div className="sidebar-account">
          <span className="avatar" aria-hidden="true">
            {user?.full_name?.slice(0, 1).toUpperCase()}
          </span>
          <div className="account-copy">
            <strong>{user?.full_name}</strong>
            <span>{user?.email}</span>
            <Badge tone={user?.role === "ADMIN" ? "accent" : "neutral"}>
              {user?.role === "ADMIN" ? "Администратор" : "Сотрудник"}
            </Badge>
          </div>
          <button
            aria-label="Выйти"
            className="logout-button"
            disabled={isLoggingOut}
            onClick={() => void handleLogout()}
            title="Выйти"
            type="button"
          >
            <LogOut size={19} />
          </button>
        </div>
      </aside>
      {menuOpen && (
        <button
          aria-label="Закрыть меню"
          className="sidebar-backdrop"
          onClick={closeMenu}
          type="button"
        />
      )}
      <div className="app-workspace">
        <header className="workspace-topbar">
          <button
            aria-expanded={menuOpen}
            aria-label="Открыть меню"
            className="menu-button"
            onClick={() => setMenuOpen(true)}
            type="button"
          >
            <Menu size={21} />
          </button>
          <div className="workspace-title">
            <strong>{currentPage.title}</strong>
            <span>{currentPage.description}</span>
          </div>
          <div className="workspace-state">
            <ShieldCheck size={17} aria-hidden="true" />
            Защищённая сессия
          </div>
        </header>
        <main className="app-content">{children}</main>
      </div>
    </div>
  );
}
