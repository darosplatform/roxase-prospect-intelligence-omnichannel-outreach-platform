"use client";

import { useState } from "react";
import { useApiList } from "@/lib/useApiList";
import { EmptyState, ErrorBanner, PageHeader, Spinner, Table } from "@/components/ui";
import type { Contact } from "@/lib/types";

export default function ContactsPage() {
  const [q, setQ] = useState("");
  const { data, error, loading } = useApiList<Contact>(
    "/api/v1/contacts",
    { limit: 100, q: q || undefined },
    [q]
  );

  return (
    <div>
      <PageHeader title="Contacts" description="People discovered or entered manually." />
      <input
        placeholder="Search by name, email, job title..."
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="mb-4 w-full max-w-sm rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
      />
      {error && <ErrorBanner message={error} />}
      {loading && <Spinner />}
      {!loading && data && data.length === 0 && <EmptyState label="No contacts yet." />}
      {!loading && data && data.length > 0 && (
        <Table columns={["Name", "Title", "Email", "Phone", "Source"]}>
          {data.map((c) => (
            <tr key={c.id} className="hover:bg-slate-50">
              <td className="px-4 py-2 font-medium text-slate-900">
                {[c.first_name, c.last_name].filter(Boolean).join(" ") || "—"}
              </td>
              <td className="px-4 py-2 text-slate-600">{c.job_title ?? "—"}</td>
              <td className="px-4 py-2 text-slate-600">{c.email ?? "—"}</td>
              <td className="px-4 py-2 text-slate-600">{c.phone ?? "—"}</td>
              <td className="px-4 py-2 text-slate-600">{c.source ?? "—"}</td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}
