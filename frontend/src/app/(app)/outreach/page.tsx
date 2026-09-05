"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApiList } from "@/lib/useApiList";
import { Badge, Button, EmptyState, ErrorBanner, PageHeader, Spinner, Table } from "@/components/ui";
import type { OutreachRequest } from "@/lib/types";

const STATUSES = ["", "approved", "denied", "queued", "dispatching", "sent", "failed", "cancelled"];

export default function OutreachPage() {
  const [status, setStatus] = useState("");
  const { data, error, loading, reload } = useApiList<OutreachRequest>(
    "/api/v1/outreach",
    { limit: 100, status: status || undefined },
    [status]
  );
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function act(id: string, action: "dispatch" | "cancel") {
    setBusyId(id);
    setActionError(null);
    try {
      await api.post(`/api/v1/outreach/${id}/${action}`);
      await reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? String(err.detail) : "Action failed");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <PageHeader
        title="Outreach"
        description="Queued, approved, denied and sent messages. The worker processes queued requests asynchronously; dispatch here simulates one poll for approved requests."
      />
      <select
        value={status}
        onChange={(e) => setStatus(e.target.value)}
        className="mb-4 rounded-md border border-slate-300 px-3 py-2 text-sm"
      >
        {STATUSES.map((s) => (
          <option key={s} value={s}>
            {s === "" ? "All statuses" : s}
          </option>
        ))}
      </select>
      {error && <ErrorBanner message={error} />}
      {actionError && <ErrorBanner message={actionError} />}
      {loading && <Spinner />}
      {!loading && data && data.length === 0 && <EmptyState label="No outreach requests yet." />}
      {!loading && data && data.length > 0 && (
        <Table columns={["Channel", "Status", "Scheduled", "Provider message", ""]}>
          {data.map((o) => (
            <tr key={o.id} className="hover:bg-slate-50">
              <td className="px-4 py-2">{o.channel}</td>
              <td className="px-4 py-2">
                <Badge value={o.status} />
              </td>
              <td className="px-4 py-2 text-slate-500">
                {o.scheduled_at ? new Date(o.scheduled_at).toLocaleString() : "—"}
              </td>
              <td className="px-4 py-2 text-slate-500">{o.provider_message_id ?? "—"}</td>
              <td className="px-4 py-2">
                <div className="flex gap-2">
                  {(o.status === "approved" || o.status === "queued") && (
                    <Button
                      variant="secondary"
                      disabled={busyId === o.id}
                      onClick={() => act(o.id, "dispatch")}
                    >
                      Dispatch
                    </Button>
                  )}
                  {(o.status === "approved" || o.status === "queued") && (
                    <Button
                      variant="danger"
                      disabled={busyId === o.id}
                      onClick={() => act(o.id, "cancel")}
                    >
                      Cancel
                    </Button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}
