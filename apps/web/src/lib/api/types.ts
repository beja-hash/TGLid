export type Role = "ADMIN" | "EMPLOYEE";

export type UserProfile = {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
  created_at?: string;
  last_login_at?: string | null;
};

export type Paginated<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type UserWithTemporaryPassword = {
  user: UserProfile;
  temporary_password: string;
};

export type AuditLog = {
  id: string;
  actor_user_id: string | null;
  event_type: string;
  target_type: string;
  target_id: string | null;
  ip_address: string | null;
  user_agent: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type SystemStatus = {
  api: "ok" | "unavailable";
  postgres: "ok" | "unavailable";
  redis: "ok" | "unavailable";
  environment: string;
};
