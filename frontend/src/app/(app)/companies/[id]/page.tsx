"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useApiList } from "@/lib/useApiList";
import { Badge, Card, ErrorBanner, PageHeader, Spinner } from "@/components/ui";
import type { Company, Contact, Evidence, Lead, Signal } from "@/lib/types";

export default function CompanyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [company, setCompany] = useState<Company | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<Company>(`/api/v1/companies/${id}`)
      .then(setCompany)
      .catch((err) => setError(err instanceof ApiError ? String(err.detail) : "Failed to load"));
  }, [id]);

  const contacts = useApiList<Contact>("/api/v1/contacts", { company_id: id, limit: 50 });
  const evidence = useApiList<Evidence>("/api/v1/evidence", { company_id: id, limit: 50 });
  const signals = useApiList<Signal>("/api/v1/signals", { company_id: id, limit: 50 });
  const leads = useApiList<Lead>("/api/v1/leads", { company_id: id, limit: 50 });

  if (error) return <ErrorBanner message={error} />;
  if (!company) return <Spinner />;

  return (
    <div>
      <PageHeader title={company.legal_name} description={company.domain ?? undefined} />

      <Card className="mb-6">
        <dl className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-slate-500">Industry</dt>
            <dd>{company.industry ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Country</dt>
            <dd>{company.country ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Employees</dt>
            <dd>{company.employee_count ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Source</dt>
            <dd>{company.source ?? "—"}</dd>
          </div>
        </dl>
      </Card>

      <Section title="Leads">
        {leads.loading && <Spinner />}
        {leads.data?.length === 0 && <p className="text-sm text-slate-500">No leads yet.</p>}
        <ul className="space-y-2">
          {leads.data?.map((l) => (
            <li key={l.id} className="flex items-center justify-between rounded-md border border-slate-200 px-3 py-2 text-sm">
              <Link href={`/leads/${l.id}`} className="underline">
                Lead {l.id.slice(0, 8)}
              </Link>
              <span className="flex items-center gap-2">
                <Badge value={l.qualification_status} />
                <span className="text-slate-500">score {l.score ?? "—"}</span>
              </span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Contacts">
        {contacts.loading && <Spinner />}
        {contacts.data?.length === 0 && <p className="text-sm text-slate-500">No contacts yet.</p>}
        <ul className="space-y-2">
          {contacts.data?.map((c) => (
            <li key={c.id} className="rounded-md border border-slate-200 px-3 py-2 text-sm">
              <span className="font-medium">
                {[c.first_name, c.last_name].filter(Boolean).join(" ") || c.email || "Unnamed"}
              </span>
              {c.job_title && <span className="text-slate-500"> · {c.job_title}</span>}
              {c.email && <span className="ml-2 text-slate-500">{c.email}</span>}
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Signals">
        {signals.loading && <Spinner />}
        {signals.data?.length === 0 && <p className="text-sm text-slate-500">No signals yet.</p>}
        <ul className="space-y-2">
          {signals.data?.map((s) => (
            <li key={s.id} className="rounded-md border border-slate-200 px-3 py-2 text-sm">
              <Badge value={s.signal_type} /> <span className="ml-2">{s.title}</span>
              <span className="ml-2 text-slate-400">confidence {s.confidence}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Evidence">
        {evidence.loading && <Spinner />}
        {evidence.data?.length === 0 && <p className="text-sm text-slate-500">No evidence yet.</p>}
        <ul className="space-y-2">
          {evidence.data?.map((e) => (
            <li key={e.id} className="rounded-md border border-slate-200 px-3 py-2 text-sm">
              <a href={e.source_url} target="_blank" rel="noreferrer" className="underline">
                {e.title ?? e.source_url}
              </a>
              <span className="ml-2 text-slate-400">
                {e.evidence_type} · confidence {e.confidence}
              </span>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-6">
      <h2 className="mb-2 text-sm font-semibold text-slate-700">{title}</h2>
      {children}
    </div>
  );
}
