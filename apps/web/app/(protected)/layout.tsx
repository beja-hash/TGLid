"use client";

import { AppShell } from "../../components/layout/app-shell";
import { RequireAuth } from "../../components/auth/route-guards";

export default function ProtectedLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <RequireAuth>
      <AppShell>{children}</AppShell>
    </RequireAuth>
  );
}
