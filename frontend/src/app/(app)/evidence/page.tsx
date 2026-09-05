"use client";

import { useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useApiList } from "@/lib/useApiList";
import { Badge, Button, EmptyState, ErrorBanner, PageHeader, Spinner, Table } from "@/components/ui";
import type { Evidence } from "@/lib/types";

export default function EvidencePage() {
  const { data, error, loading } = useApiList<Evidence>("/api/v1/evidence", {
    limit: 100,
  });
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function detectSignal(evidenceId: string) {
    setBusyId(evidenceId);
    setActionError(null);
    try {
      const signal = await api.post(`/api/v1/evidence/${evidenceId}/detect-signal`);
      if (!signal) {
        setActionError("No signal detected from this evidence (that's a valid outcome).");
      }
    } catch (err) {
      setActionError(err instanceof ApiError ? String(err.detail) : "Failed");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <PageHeader
        title="Evidence"
        description="Provenance-preserving observations. What was seen, where, when, with what confidence."
      />
      {error && <ErrorBanner message={error} />}
      {actionError && <ErrorBanner message={actionError} />}
      {loading && <Spinner />}
      {!loading && data && data.length === 0 && <EmptyState label="No evidence yet." />}
      {!loading && data && data.length > 0 && (
        <Table columns={["Title", "Type", "Source", "Confidence", "Collected", ""]}>
          {data.map((e) => (
            <tr key={e.id} className="hover:bg-slate-50">
              <td className="max-w-xs truncate px-4 py-2 font-medium text-slate-900">
                {e.title ?? "(untitled)"}
              </td>
              <td className="px-4 py-2">
                <Badge value={e.evidence_type} />
              </td>
              <td className="px-4 py-2">
                <a
                  href={e.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-slate-600 underline"
                >
                  {e.source_name ?? e.source_url}
                </a>
              </td>
              <td className="px-4 py-2 text-slate-600">{e.confidence}</td>
              <td className="px-4 py-2 text-slate-500">
                {new Date(e.collected_at).toLocaleDateString()}
              </td>
              <td className="px-4 py-2">
                <div className="flex items-center gap-2">
                  {e.company_id && (
                    <Link href={`/companies/${e.company_id}`} className="text-xs underline">
                      Company
                    </Link>
                  )}
                  <Button
                    variant="secondary"
                    disabled={busyId === e.id}
                    onClick={() => detectSignal(e.id)}
                  >
                    Detect signal
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}
