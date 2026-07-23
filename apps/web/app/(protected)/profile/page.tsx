"use client";

import { KeyRound, Mail, ShieldCheck, UserRound } from "lucide-react";
import Link from "next/link";

import {
  Badge,
  Card,
  PageHeader,
  SectionHeader,
  StatusBadge,
} from "../../../components/ui/primitives";
import { useAuth } from "../../../src/lib/auth/context";

export default function ProfilePage() {
  const { user } = useAuth();
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Учётная запись"
        title="Профиль"
        description="Личные данные и параметры доступа к TGLid."
      />
      <div className="profile-grid">
        <Card>
          <SectionHeader
            title="Основная информация"
            description="Эти данные управляются администратором."
          />
          <div className="profile-identity">
            <span className="profile-avatar" aria-hidden="true">
              {user?.full_name?.slice(0, 1).toUpperCase()}
            </span>
            <div>
              <h3>{user?.full_name}</h3>
              <p>{user?.email}</p>
            </div>
          </div>
          <dl className="detail-list">
            <div>
              <dt>
                <UserRound size={17} /> Имя
              </dt>
              <dd>{user?.full_name}</dd>
            </div>
            <div>
              <dt>
                <Mail size={17} /> Email
              </dt>
              <dd className="breakable">{user?.email}</dd>
            </div>
            <div>
              <dt>
                <ShieldCheck size={17} /> Роль
              </dt>
              <dd>
                <Badge tone={user?.role === "ADMIN" ? "accent" : "neutral"}>
                  {user?.role === "ADMIN" ? "Администратор" : "Сотрудник"}
                </Badge>
              </dd>
            </div>
            <div>
              <dt>Статус учётной записи</dt>
              <dd>
                <StatusBadge active={Boolean(user?.is_active)} />
              </dd>
            </div>
          </dl>
        </Card>

        <Card>
          <SectionHeader
            title="Безопасность"
            description="Контролируйте доступ к своей учётной записи."
          />
          <div className="security-status">
            <span className="security-icon" aria-hidden="true">
              <KeyRound size={22} />
            </span>
            <div>
              <strong>Пароль</strong>
              <p>
                {user?.must_change_password
                  ? "Используется временный пароль"
                  : "Постоянный пароль установлен"}
              </p>
            </div>
            <Badge tone={user?.must_change_password ? "warning" : "success"}>
              {user?.must_change_password ? "Нужно сменить" : "Защищено"}
            </Badge>
          </div>
          <Link className="button button-primary" href="/change-password">
            <KeyRound size={18} />
            Сменить пароль
          </Link>
        </Card>
      </div>
    </div>
  );
}
