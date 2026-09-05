"use client";

import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "./auth";
import type { TokenResponse } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `API error ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

let refreshInFlight: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!res.ok) return false;
        const data = (await res.json()) as TokenResponse;
        setTokens(data.access_token, data.refresh_token);
        return true;
      } catch {
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

interface RequestOptions {
  method?: string;
  json?: unknown;
  params?: Record<string, string | number | boolean | undefined | null>;
  /** Skip the automatic Authorization header (login/register only). */
  anonymous?: boolean;
}

function buildUrl(path: string, params?: RequestOptions["params"]): string {
  const url = new URL(`${API_BASE_URL}${path}`);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", json, params, anonymous = false } = options;

  const doFetch = async (): Promise<Response> => {
    const headers: Record<string, string> = {};
    if (json !== undefined) headers["Content-Type"] = "application/json";
    if (!anonymous) {
      const token = getAccessToken();
      if (token) headers.Authorization = `Bearer ${token}`;
    }
    return fetch(buildUrl(path, params), {
      method,
      headers,
      body: json !== undefined ? JSON.stringify(json) : undefined,
    });
  };

  let res = await doFetch();

  if (res.status === 401 && !anonymous) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      res = await doFetch();
    } else {
      clearTokens();
      if (typeof window !== "undefined") {
        // A plain module has no router hook to call; a full navigation
        // also guarantees every component's in-memory state is cleared
        // after an auth failure, not just re-rendered.
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        window.location.href = "/login";
      }
      throw new ApiError(401, "Session expired");
    }
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const text = await res.text();
  const data = text ? JSON.parse(text) : null;

  if (!res.ok) {
    throw new ApiError(res.status, data?.detail ?? data);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, params?: RequestOptions["params"]) =>
    request<T>(path, { method: "GET", params }),
  post: <T>(path: string, json?: unknown, options?: Partial<RequestOptions>) =>
    request<T>(path, { method: "POST", json, ...options }),
  patch: <T>(path: string, json?: unknown) => request<T>(path, { method: "PATCH", json }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
