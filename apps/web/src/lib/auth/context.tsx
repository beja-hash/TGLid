"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { api, ApiError, setUnauthorizedHandler } from "../api/client";
import type { UserProfile } from "../api/types";

type AuthState = "loading" | "authenticated" | "anonymous" | "unavailable";
type AuthContextValue = {
  state: AuthState;
  user: UserProfile | null;
  login: (email: string, password: string) => Promise<UserProfile>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<UserProfile | null>;
  setUser: (user: UserProfile | null) => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const [state, setState] = useState<AuthState>("loading");
  const [user, setUser] = useState<UserProfile | null>(null);

  const clearAuthentication = useCallback(() => {
    setUser(null);
    setState("anonymous");
  }, []);

  const refreshProfile = useCallback(async (): Promise<UserProfile | null> => {
    try {
      const profile = await api.me();
      setUser(profile);
      setState("authenticated");
      return profile;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        clearAuthentication();
      } else {
        setState("unavailable");
      }
      return null;
    }
  }, [clearAuthentication]);

  useEffect(() => {
    setUnauthorizedHandler(clearAuthentication);
    void refreshProfile();
    return () => setUnauthorizedHandler(undefined);
  }, [clearAuthentication, refreshProfile]);

  const value = useMemo<AuthContextValue>(
    () => ({
      state,
      user,
      login: async (email, password) => {
        const profile = await api.login(email.trim(), password);
        setUser(profile);
        setState("authenticated");
        return profile;
      },
      logout: async () => {
        try {
          await api.logout();
        } finally {
          clearAuthentication();
        }
      },
      refreshProfile,
      setUser,
    }),
    [clearAuthentication, refreshProfile, state, user],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return value;
}
