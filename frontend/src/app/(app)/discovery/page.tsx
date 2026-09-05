"use client";

import { useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useApiList } from "@/lib/useApiList";
import { Badge, Button, Card, EmptyState, ErrorBanner, PageHeader, Spinner, Table } from "@/components/ui";
import type { DiscoveryJob } from "@/lib/types";

export default function DiscoveryPage() {
  const { data, error, loading, reload } = useApiList<DiscoveryJob>("/api/v1/discovery/jobs", {
    limit: 100,
  });
  const [target, setTarget] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function createJob() {
    setSubmitting(true);
    setFormError(null);
    try {
      await api.post("/api/v1/discovery/jobs", { target, source_type: "url" });
      setTarget("");
      setShowForm(false);
      await reload();
    } catch (err) {
      setFormError(err instanceof ApiError ? String(err.detail) : "Failed to create job");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Discovery"
        description="Jobs that turn a public URL into securely-fetched, extracted, signal-detected evidence."
        actions={
          <Button onClick={() => setShowForm((v) => !v)}>
            {showForm ? "Cancel" : "New job"}
          </Button>
        }
      />

      {showForm && (
        <Card className="mb-6">
          {formError && <ErrorBanner message={formError} />}
          <label className="mb-1 block text-xs font-medium text-slate-700">
            Target (company website)
          </label>
          <div className="flex gap-2">
            <input
              placeholder="https://example.com"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
            <Button onClick={createJob} disabled={submitting || !target}>
              Create
            </Button>
          </div>
        </Card>
      )}

      {error && <ErrorBanner message={error} />}
      {loading && <Spinner />}
      {!loading && data && data.length === 0 && <EmptyState label="No discovery jobs yet." />}
      {!loading && data && data.length > 0 && (
        <Table columns={["Target", "Status", "Attempts", "Last error", "Created"]}>
          {data.map((j) => (
            <tr key={j.id} className="hover:bg-slate-50">
              <td className="px-4 py-2">
                <Link href={`/discovery/${j.id}`} className="font-medium text-slate-900 underline">
                  {j.target}
                </Link>
              </td>
              <td className="px-4 py-2">
                <Badge value={j.status} />
              </td>
              <td className="px-4 py-2 text-slate-600">{j.attempt_count}</td>
              <td className="max-w-xs truncate px-4 py-2 text-red-600">{j.last_error ?? "—"}</td>
              <td className="px-4 py-2 text-slate-500">
                {new Date(j.created_at).toLocaleString()}
              </td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}
