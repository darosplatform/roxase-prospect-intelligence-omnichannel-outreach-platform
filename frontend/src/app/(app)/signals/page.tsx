"use client";

import { useState } from "react";
import Link from "next/link";
import { useApiList } from "@/lib/useApiList";
import { Badge, EmptyState, ErrorBanner, PageHeader, Spinner, Table } from "@/components/ui";
import type { Signal } from "@/lib/types";

const SIGNAL_TYPES = [
  "",
  "hiring",
  "expansion",
  "funding",
  "product_launch",
  "partnership",
  "leadership_change",
  "migration",
  "certification",
  "acquisition",
  "other",
];

export default function SignalsPage() {
  const [signalType, setSignalType] = useState("");
  const { data, error, loading } = useApiList<Signal>(
    "/api/v1/signals",
    { limit: 100, signal_type: signalType || undefined },
    [signalType]
  );

  return (
    <div>
      <PageHeader title="Signals" description="Business events detected from Evidence." />
      <select
        value={signalType}
        onChange={(e) => setSignalType(e.target.value)}
        className="mb-4 rounded-md border border-slate-300 px-3 py-2 text-sm"
      >
        {SIGNAL_TYPES.map((t) => (
          <option key={t} value={t}>
            {t === "" ? "All types" : t}
          </option>
        ))}
      </select>
      {error && <ErrorBanner message={error} />}
      {loading && <Spinner />}
      {!loading && data && data.length === 0 && <EmptyState label="No signals yet." />}
      {!loading && data && data.length > 0 && (
        <Table columns={["Type", "Title", "Company", "Confidence", "Status", "Detected"]}>
          {data.map((s) => (
            <tr key={s.id} className="hover:bg-slate-50">
              <td className="px-4 py-2">
                <Badge value={s.signal_type} />
              </td>
              <td className="px-4 py-2 text-slate-900">{s.title ?? "—"}</td>
              <td className="px-4 py-2">
                <Link href={`/companies/${s.company_id}`} className="text-sm underline">
                  {s.company_id.slice(0, 8)}
                </Link>
              </td>
              <td className="px-4 py-2 text-slate-600">{s.confidence}</td>
              <td className="px-4 py-2">
                <Badge value={s.status} />
              </td>
              <td className="px-4 py-2 text-slate-500">
                {new Date(s.detected_at).toLocaleDateString()}
              </td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}
