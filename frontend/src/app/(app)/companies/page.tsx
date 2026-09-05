"use client";

import { useState } from "react";
import Link from "next/link";
import { useApiList } from "@/lib/useApiList";
import { EmptyState, ErrorBanner, PageHeader, Spinner, Table } from "@/components/ui";
import type { Company } from "@/lib/types";

export default function CompaniesPage() {
  const [q, setQ] = useState("");
  const { data, error, loading } = useApiList<Company>(
    "/api/v1/companies",
    { limit: 100, q: q || undefined },
    [q]
  );

  return (
    <div>
      <PageHeader title="Companies" description="Every company observed or entered manually." />
      <input
        placeholder="Search by name, domain, industry..."
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="mb-4 w-full max-w-sm rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
      />
      {error && <ErrorBanner message={error} />}
      {loading && <Spinner />}
      {!loading && data && data.length === 0 && <EmptyState label="No companies yet." />}
      {!loading && data && data.length > 0 && (
        <Table columns={["Name", "Domain", "Industry", "Country", "Source"]}>
          {data.map((c) => (
            <tr key={c.id} className="hover:bg-slate-50">
              <td className="px-4 py-2">
                <Link href={`/companies/${c.id}`} className="font-medium text-slate-900 underline">
                  {c.legal_name}
                </Link>
              </td>
              <td className="px-4 py-2 text-slate-600">{c.domain ?? "—"}</td>
              <td className="px-4 py-2 text-slate-600">{c.industry ?? "—"}</td>
              <td className="px-4 py-2 text-slate-600">{c.country ?? "—"}</td>
              <td className="px-4 py-2 text-slate-600">{c.source ?? "—"}</td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}
