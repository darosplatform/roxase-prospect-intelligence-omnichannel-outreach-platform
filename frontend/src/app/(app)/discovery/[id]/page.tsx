"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { Badge, Button, Card, ErrorBanner, PageHeader, Spinner } from "@/components/ui";
import type { DiscoveryJob, DiscoverySource } from "@/lib/types";

export default function DiscoveryJobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [job, setJob] = useState<DiscoveryJob | null>(null);
  const [sources, setSources] = useState<DiscoverySource[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newUrl, setNewUrl] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  async function reload() {
    try {
      const [j, s] = await Promise.all([
        api.get<DiscoveryJob>(`/api/v1/discovery/jobs/${id}`),
        api.get<DiscoverySource[]>(`/api/v1/discovery/jobs/${id}/sources`),
      ]);
      setJob(j);
      setSources(s);
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Failed to load");
    }
  }

  useEffect(() => {
    // Fetch-on-mount/on-id-change: standard for a client-rendered detail
    // page against a Bearer-token API.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function addSource() {
    setBusy("add");
    setError(null);
    try {
      await api.post(`/api/v1/discovery/jobs/${id}/sources`, [{ url: newUrl }]);
      setNewUrl("");
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Failed to add source");
    } finally {
      setBusy(null);
    }
  }

  async function fetchSource(sourceId: string) {
    setBusy(sourceId);
    setError(null);
    try {
      await api.post(`/api/v1/discovery/sources/${sourceId}/fetch`);
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Fetch failed");
    } finally {
      setBusy(null);
    }
  }

  async function extractSource(sourceId: string) {
    setBusy(sourceId);
    setError(null);
    try {
      await api.post(`/api/v1/discovery/sources/${sourceId}/extract`);
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Extraction failed");
    } finally {
      setBusy(null);
    }
  }

  if (error && !job) return <ErrorBanner message={error} />;
  if (!job) return <Spinner />;

  return (
    <div>
      <PageHeader title={job.target} description={`Job status: ${job.status}`} />
      {error && <ErrorBanner message={error} />}

      <Card className="mb-6">
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-slate-500">Status</dt>
            <dd><Badge value={job.status} /></dd>
          </div>
          <div>
            <dt className="text-slate-500">Attempts</dt>
            <dd>{job.attempt_count}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Started</dt>
            <dd>{job.started_at ? new Date(job.started_at).toLocaleString() : "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Finished</dt>
            <dd>{job.finished_at ? new Date(job.finished_at).toLocaleString() : "—"}</dd>
          </div>
        </dl>
        {job.last_error && (
          <p className="mt-3 text-sm text-red-600">Last error: {job.last_error}</p>
        )}
      </Card>

      <h2 className="mb-2 text-sm font-semibold text-slate-700">Sources</h2>
      <Card className="mb-4">
        <div className="flex gap-2">
          <input
            placeholder="https://example.com/about"
            value={newUrl}
            onChange={(e) => setNewUrl(e.target.value)}
            className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <Button onClick={addSource} disabled={busy === "add" || !newUrl}>
            Add source
          </Button>
        </div>
      </Card>

      <div className="space-y-2">
        {sources?.map((s) => (
          <Card key={s.id}>
            <div className="flex items-center justify-between">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{s.url}</p>
                <p className="mt-1 text-xs text-slate-500">
                  <Badge value={s.status} />
                  {s.validation_status && (
                    <span className="ml-2">{s.validation_status}</span>
                  )}
                  {s.rejection_reason && (
                    <span className="ml-2 text-red-600">{s.rejection_reason}</span>
                  )}
                </p>
              </div>
              <div className="ml-4 flex shrink-0 gap-2">
                {(s.status === "pending" || s.status === "eligible") && (
                  <Button
                    variant="secondary"
                    disabled={busy === s.id}
                    onClick={() => fetchSource(s.id)}
                  >
                    Fetch
                  </Button>
                )}
                {s.status === "fetched" && (
                  <Button
                    variant="secondary"
                    disabled={busy === s.id}
                    onClick={() => extractSource(s.id)}
                  >
                    Extract
                  </Button>
                )}
              </div>
            </div>
          </Card>
        ))}
        {sources?.length === 0 && (
          <p className="text-sm text-slate-500">No sources yet — add one above.</p>
        )}
      </div>
    </div>
  );
}
