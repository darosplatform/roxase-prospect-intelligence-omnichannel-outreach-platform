"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useApiList } from "@/lib/useApiList";
import { Badge, Button, Card, ErrorBanner, PageHeader, Spinner } from "@/components/ui";
import type { Evidence, Lead } from "@/lib/types";

const QUAL_OPTIONS = ["candidate", "qualified", "disqualified"];

export default function LeadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [lead, setLead] = useState<Lead | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [qualStatus, setQualStatus] = useState("qualified");
  const [reason, setReason] = useState("");
  const [selectedEvidence, setSelectedEvidence] = useState<Set<string>>(new Set());

  async function reload() {
    try {
      const data = await api.get<Lead>(`/api/v1/leads/${id}`);
      setLead(data);
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Failed to load");
    }
  }

  useEffect(() => {
    // Fetch-on-mount/on-id-change: standard for a client-rendered detail
    // page against a Bearer-token API (no server-side fetch available here
    // without a cookie-based session).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const evidence = useApiList<Evidence>(
    "/api/v1/evidence",
    { company_id: lead?.company_id ?? undefined, limit: 50 },
    [lead?.company_id]
  );

  async function computeScore() {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/api/v1/leads/${id}/score`);
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Failed to score");
    } finally {
      setBusy(false);
    }
  }

  async function qualify() {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/api/v1/leads/${id}/qualify`, {
        status: qualStatus,
        reason: reason || undefined,
        evidence_ids: Array.from(selectedEvidence),
      });
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : "Failed to qualify");
    } finally {
      setBusy(false);
    }
  }

  function toggleEvidence(evId: string) {
    setSelectedEvidence((prev) => {
      const next = new Set(prev);
      if (next.has(evId)) next.delete(evId);
      else next.add(evId);
      return next;
    });
  }

  if (error && !lead) return <ErrorBanner message={error} />;
  if (!lead) return <Spinner />;

  const breakdown = lead.score_explanation?.breakdown;
  const factors = lead.score_explanation?.factors ?? [];

  return (
    <div>
      <PageHeader
        title={`Lead ${lead.id.slice(0, 8)}`}
        description={
          lead.company_id ? undefined : "No company attached"
        }
        actions={
          lead.company_id ? (
            <Link href={`/companies/${lead.company_id}`} className="text-sm underline">
              View company
            </Link>
          ) : undefined
        }
      />
      {error && <ErrorBanner message={error} />}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <h2 className="mb-3 text-sm font-semibold text-slate-700">Status</h2>
          <dl className="space-y-2 text-sm">
            <Row label="Status"><Badge value={lead.status} /></Row>
            <Row label="Qualification"><Badge value={lead.qualification_status} /></Row>
            <Row label="Score">
              <span className="text-lg font-semibold">{lead.score ?? "—"}</span>
              {lead.scoring_version && (
                <span className="ml-2 text-xs text-slate-400">({lead.scoring_version})</span>
              )}
            </Row>
            {lead.qualification_reason && (
              <Row label="Reason">{lead.qualification_reason}</Row>
            )}
          </dl>
          <div className="mt-4">
            <Button onClick={computeScore} disabled={busy} variant="secondary">
              Compute score
            </Button>
          </div>
        </Card>

        <Card>
          <h2 className="mb-3 text-sm font-semibold text-slate-700">Score breakdown</h2>
          {breakdown ? (
            <ul className="space-y-1 text-sm">
              {Object.entries(breakdown).map(([k, v]) => (
                <li key={k} className="flex justify-between">
                  <span className="capitalize text-slate-600">{k.replace("_", " ")}</span>
                  <span className="font-medium">{v}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">Not scored yet.</p>
          )}
          {factors.length > 0 && (
            <div className="mt-4">
              <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">Factors</h3>
              <ul className="space-y-1 text-sm">
                {factors.map((f, i) => (
                  <li key={i} className="flex justify-between">
                    <span>{f.name}</span>
                    <span className="text-slate-500">{f.impact}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      </div>

      <Card className="mt-6">
        <h2 className="mb-3 text-sm font-semibold text-slate-700">Qualify this lead</h2>
        <p className="mb-3 text-xs text-slate-500">
          Select the evidence that supports this decision — a lead can never be
          qualified on a score alone.
        </p>
        <div className="mb-3 space-y-1">
          {evidence.data?.map((e) => (
            <label key={e.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={selectedEvidence.has(e.id)}
                onChange={() => toggleEvidence(e.id)}
              />
              <span>{e.title ?? e.source_url}</span>
            </label>
          ))}
          {evidence.data?.length === 0 && (
            <p className="text-sm text-slate-500">No evidence available for this company.</p>
          )}
        </div>
        <div className="flex items-end gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-700">Decision</label>
            <select
              value={qualStatus}
              onChange={(e) => setQualStatus(e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm"
            >
              {QUAL_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div className="flex-1">
            <label className="mb-1 block text-xs font-medium text-slate-700">Reason</label>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <Button onClick={qualify} disabled={busy}>
            Submit
          </Button>
        </div>
      </Card>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-slate-500">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}
