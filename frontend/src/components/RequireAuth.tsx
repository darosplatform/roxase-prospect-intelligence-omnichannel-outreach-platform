"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";

/** Client-side gate ONLY: hides the shell before a token check completes and
 * redirects when there is none. This is a UX convenience, never a security
 * boundary — every actual authorization decision is re-checked by the API
 * on each request (RBAC, tenant isolation), independent of anything this
 * component does. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">
        Loading...
      </div>
    );
  }

  return <>{children}</>;
}
