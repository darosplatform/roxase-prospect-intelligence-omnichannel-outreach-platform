"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { clearTokens, getCurrentUser, setTokens } from "@/lib/auth";
import { api } from "@/lib/api";
import type { JwtPayload, TokenResponse } from "@/lib/types";

interface AuthContextValue {
  user: JwtPayload | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (slug: string, email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<JwtPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    // Deferred to an effect deliberately: localStorage doesn't exist during
    // SSR, so reading it during the initial render (e.g. via a useState
    // lazy initializer) would make the client's first render diverge from
    // the server-rendered HTML and trigger a hydration mismatch.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setUser(getCurrentUser());
    setLoading(false);
  }, []);

  async function login(email: string, password: string) {
    const data = await api.post<TokenResponse>(
      "/api/v1/auth/login",
      { email, password },
      { anonymous: true }
    );
    setTokens(data.access_token, data.refresh_token);
    setUser(getCurrentUser());
    router.push("/dashboard");
  }

  async function register(slug: string, email: string, password: string, fullName?: string) {
    const data = await api.post<TokenResponse>(
      "/api/v1/auth/register",
      { email, password, full_name: fullName },
      { anonymous: true, params: { slug } }
    );
    setTokens(data.access_token, data.refresh_token);
    setUser(getCurrentUser());
    router.push("/dashboard");
  }

  function logout() {
    clearTokens();
    setUser(null);
    router.push("/login");
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
