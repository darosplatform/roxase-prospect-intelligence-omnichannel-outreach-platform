"use client";

import { useState } from "react";
import { useApiList } from "@/lib/useApiList";
import { EmptyState, ErrorBanner, PageHeader, Spinner, Table } from "@/components/ui";
import type { AuditEvent } from "@/lib/types";

export default function AuditPage() {
  const [entityType, setEntityType] = useState("");
  const { data, error, loading } = useApiList<AuditEvent>(
    "/api/v1/audit",
    { limit: 100, entity_type: entityType || undefined },
    [entityType]
  );

  return (
    <div>
      <PageHeader title="Audit" description="Every recorded action: who did what, to what, when." />
      <input
        placeholder="Filter by entity type (e.g. lead, signal, campaign)..."
        value={entityType}
        onChange={(e) => setEntityType(e.target.value)}
        className="mb-4 w-full max-w-sm rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
      />
      {error && <ErrorBanner message={error} />}
      {loading && <Spinner />}
      {!loading && data && data.length === 0 && <EmptyState label="No audit events yet." />}
      {!loading && data && data.length > 0 && (
        <Table columns={["Action", "Entity", "Actor", "When"]}>
          {data.map((e) => (
            <tr key={e.id} className="hover:bg-slate-50">
              <td className="px-4 py-2 font-medium text-slate-900">{e.action}</td>
              <td className="px-4 py-2 text-slate-600">
                {e.entity_type}
                {e.entity_id && (
                  <span className="ml-1 text-xs text-slate-400">{e.entity_id.slice(0, 8)}</span>
                )}
              </td>
              <td className="px-4 py-2 text-slate-600">
                {e.actor_user_id ? e.actor_user_id.slice(0, 8) : "system"}
              </td>
              <td className="px-4 py-2 text-slate-500">
                {new Date(e.created_at).toLocaleString()}
              </td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}
