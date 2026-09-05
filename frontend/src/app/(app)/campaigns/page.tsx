"use client";

import { useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useApiList } from "@/lib/useApiList";
import { Badge, Button, Card, EmptyState, ErrorBanner, PageHeader, Spinner, Table } from "@/components/ui";
import type { Campaign } from "@/lib/types";

export default function CampaignsPage() {
  const { data, error, loading, reload } = useApiList<Campaign>("/api/v1/campaigns", {
    limit: 100,
  });
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [channel, setChannel] = useState("email");
  const [dryRun, setDryRun] = useState(true);
  const [minScore, setMinScore] = useState(1);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function createCampaign() {
    setSubmitting(true);
    setFormError(null);
    try {
      await api.post("/api/v1/campaigns", {
        name,
        status: "draft",
        channel,
        policy: {
          dry_run: dryRun,
          allowed_channels: [channel],
          min_lead_score: minScore,
          require_qualification: true,
          require_evidence: true,
        },
      });
      setShowForm(false);
      setName("");
      await reload();
    } catch (err) {
      setFormError(err instanceof ApiError ? String(err.detail) : "Failed to create");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Campaigns"
        description="Outreach campaigns and their policy configuration."
        actions={
          <Button onClick={() => setShowForm((v) => !v)}>
            {showForm ? "Cancel" : "New campaign"}
          </Button>
        }
      />

      {showForm && (
        <Card className="mb-6">
          {formError && <ErrorBanner message={formError} />}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700">Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700">Channel</label>
              <select
                value={channel}
                onChange={(e) => setChannel(e.target.value)}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="email">email</option>
                <option value="whatsapp">whatsapp</option>
                <option value="telegram">telegram</option>
                <option value="messenger">messenger</option>
                <option value="instagram">instagram</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700">
                Minimum lead score
              </label>
              <input
                type="number"
                min={0}
                max={100}
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={dryRun}
                  onChange={(e) => setDryRun(e.target.checked)}
                />
                Dry-run (no real sends)
              </label>
            </div>
          </div>
          <div className="mt-4">
            <Button onClick={createCampaign} disabled={submitting || !name}>
              Create
            </Button>
          </div>
        </Card>
      )}

      {error && <ErrorBanner message={error} />}
      {loading && <Spinner />}
      {!loading && data && data.length === 0 && <EmptyState label="No campaigns yet." />}
      {!loading && data && data.length > 0 && (
        <Table columns={["Name", "Channel", "Status", "Dry-run", "Min score"]}>
          {data.map((c) => (
            <tr key={c.id} className="hover:bg-slate-50">
              <td className="px-4 py-2">
                <Link href={`/campaigns/${c.id}`} className="font-medium text-slate-900 underline">
                  {c.name}
                </Link>
              </td>
              <td className="px-4 py-2 text-slate-600">{c.channel}</td>
              <td className="px-4 py-2">
                <Badge value={c.status} />
              </td>
              <td className="px-4 py-2 text-slate-600">{c.policy?.dry_run ? "yes" : "no"}</td>
              <td className="px-4 py-2 text-slate-600">{c.policy?.min_lead_score ?? "—"}</td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}
