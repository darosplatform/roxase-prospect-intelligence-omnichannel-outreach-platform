"use client";

import { useState } from "react";
import Link from "next/link";
import { useApiList } from "@/lib/useApiList";
import { Badge, EmptyState, ErrorBanner, PageHeader, Spinner, Table } from "@/components/ui";
import type { Lead } from "@/lib/types";

const QUAL_STATUSES = ["", "unqualified", "candidate", "qualified", "disqualified"];

export default function LeadsPage() {
  const [qualStatus, setQualStatus] = useState("");
  const { data, error, loading } = useApiList<Lead>(
    "/api/v1/leads",
    { limit: 100, qual_status: qualStatus || undefined, sort: "-score" },
    [qualStatus]
  );

  return (
    <div>
      <PageHeader title="Leads" description="Scored, qualifiable prospects." />
      <select
        value={qualStatus}
        onChange={(e) => setQualStatus(e.target.value)}
        className="mb-4 rounded-md border border-slate-300 px-3 py-2 text-sm"
      >
        {QUAL_STATUSES.map((s) => (
          <option key={s} value={s}>
            {s === "" ? "All qualification statuses" : s}
          </option>
        ))}
      </select>
      {error && <ErrorBanner message={error} />}
      {loading && <Spinner />}
      {!loading && data && data.length === 0 && <EmptyState label="No leads yet." />}
      {!loading && data && data.length > 0 && (
        <Table columns={["Lead", "Company", "Status", "Qualification", "Score"]}>
          {data.map((l) => (
            <tr key={l.id} className="hover:bg-slate-50">
              <td className="px-4 py-2">
                <Link href={`/leads/${l.id}`} className="font-medium text-slate-900 underline">
                  {l.id.slice(0, 8)}
                </Link>
              </td>
              <td className="px-4 py-2 text-slate-600">
                {l.company_id ? (
                  <Link href={`/companies/${l.company_id}`} className="underline">
                    {l.company_id.slice(0, 8)}
                  </Link>
                ) : (
                  "—"
                )}
              </td>
              <td className="px-4 py-2">
                <Badge value={l.status} />
              </td>
              <td className="px-4 py-2">
                <Badge value={l.qualification_status} />
              </td>
              <td className="px-4 py-2 font-medium text-slate-900">{l.score ?? "—"}</td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}
