"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Card, PageHeader } from "@/components/ui";
import type { Company, Lead, Signal, DiscoveryJob, OutreachRequest } from "@/lib/types";

interface Stat {
  label: string;
  href: string;
  count: number | null;
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stat[]>([
    { label: "Companies", href: "/companies", count: null },
    { label: "Leads", href: "/leads", count: null },
    { label: "Signals", href: "/signals", count: null },
    { label: "Discovery jobs", href: "/discovery", count: null },
    { label: "Outreach requests", href: "/outreach", count: null },
  ]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const [companies, leads, signals, jobs, outreach] = await Promise.allSettled([
        api.get<Company[]>("/api/v1/companies", { limit: 200 }),
        api.get<Lead[]>("/api/v1/leads", { limit: 200 }),
        api.get<Signal[]>("/api/v1/signals", { limit: 200 }),
        api.get<DiscoveryJob[]>("/api/v1/discovery/jobs", { limit: 200 }),
        api.get<OutreachRequest[]>("/api/v1/outreach", { limit: 200 }),
      ]);
      if (cancelled) return;
      const countOf = (r: PromiseSettledResult<unknown[]>) =>
        r.status === "fulfilled" ? r.value.length : null;
      setStats([
        { label: "Companies", href: "/companies", count: countOf(companies) },
        { label: "Leads", href: "/leads", count: countOf(leads) },
        { label: "Signals", href: "/signals", count: countOf(signals) },
        { label: "Discovery jobs", href: "/discovery", count: countOf(jobs) },
        { label: "Outreach requests", href: "/outreach", count: countOf(outreach) },
      ]);
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Overview of your ROXASE workspace."
      />
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        {stats.map((s) => (
          <Link key={s.label} href={s.href}>
            <Card className="transition hover:border-slate-400">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                {s.label}
              </p>
              <p className="mt-2 text-2xl font-semibold text-slate-900">
                {s.count === null ? "—" : s.count}
              </p>
            </Card>
          </Link>
        ))}
      </div>

      <div className="mt-8">
        <h2 className="mb-3 text-sm font-semibold text-slate-700">The pipeline</h2>
        <Card>
          <p className="text-sm text-slate-600">
            Discovery → Secure Fetch → Extraction → Evidence → Signal → Lead →
            Qualification → Score → Campaign → Policy → Outreach → Worker → Provider.
            Every step is traceable back to its source URL — see a Lead&apos;s
            detail page for the full chain.
          </p>
        </Card>
      </div>
    </div>
  );
}
