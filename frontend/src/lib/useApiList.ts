"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "./api";

/** Fetch a GET list endpoint, tracking loading/error state. `deps` re-runs
 * the fetch (e.g. when a filter changes). Exposes `reload` for actions that
 * mutate data and need to refresh the list afterward. */
export function useApiList<T>(
  path: string,
  params?: Record<string, string | number | boolean | undefined | null>,
  deps: unknown[] = []
) {
  const [data, setData] = useState<T[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const paramsKey = useMemo(() => JSON.stringify(params ?? {}), [params]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.get<T[]>(path, params);
      setData(result);
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail ?? err.message) : "Failed to load");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, paramsKey]);

  useEffect(() => {
    // Fetch-on-mount/on-filter-change: standard for a client-rendered list
    // page against a Bearer-token API (no server-side fetch available here
    // without a cookie-based session).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, ...deps]);

  return { data, error, loading, reload: load };
}
