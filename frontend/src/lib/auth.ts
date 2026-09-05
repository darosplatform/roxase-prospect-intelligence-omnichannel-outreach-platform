"use client";

import type { JwtPayload, Role } from "./types";

// SECURITY NOTE (frontend never a security boundary — the backend is):
// the API is Bearer-token auth (Authorization header), not cookie-based, so
// the token must be readable by client JS to attach it to each fetch. That
// rules out an httpOnly cookie, which would otherwise be the stronger
// choice against XSS. localStorage is the pragmatic fit for the backend's
// existing contract; it is still XSS-exposed like any client-readable
// token store, which is exactly why every authorization decision that
// matters (RBAC, tenant isolation, policy) is re-enforced server-side and
// never trusted from anything read here.
const ACCESS_TOKEN_KEY = "roxase_access_token";
const REFRESH_TOKEN_KEY = "roxase_refresh_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(ACCESS_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(REFRESH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setTokens(accessToken: string, refreshToken: string): void {
  try {
    window.localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
    window.localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  } catch {
    // Storage unavailable (private mode, quota) — the user will simply be
    // asked to log in again on next navigation; nothing to recover here.
  }
}

export function clearTokens(): void {
  try {
    window.localStorage.removeItem(ACCESS_TOKEN_KEY);
    window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  } catch {
    // no-op
  }
}

/** Decode (never verify — that's the server's job) the JWT payload for
 * display/UI purposes only: current role, tenant, expiry. */
export function decodeToken(token: string): JwtPayload | null {
  try {
    const [, payloadB64] = token.split(".");
    if (!payloadB64) return null;
    const json = atob(payloadB64.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(json) as JwtPayload;
  } catch {
    return null;
  }
}

export function isTokenExpired(payload: JwtPayload): boolean {
  return payload.exp * 1000 <= Date.now();
}

export function getCurrentUser(): JwtPayload | null {
  const token = getAccessToken();
  if (!token) return null;
  const payload = decodeToken(token);
  if (!payload || isTokenExpired(payload)) return null;
  return payload;
}

// Role hierarchy for UI affordances ONLY (hide/show buttons). The backend
// re-checks every mutating request independently via require_role() — this
// list existing here is never itself an authorization boundary.
const ROLE_RANK: Record<Role, number> = {
  viewer: 0,
  operator: 1,
  analyst: 2,
  manager: 3,
  admin: 4,
  owner: 5,
};

export function hasAtLeastRole(role: Role | undefined, minimum: Role): boolean {
  if (!role) return false;
  return ROLE_RANK[role] >= ROLE_RANK[minimum];
}
