"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useApiList } from "@/lib/useApiList";
import { Badge, Card, ErrorBanner, PageHeader, Spinner, Table } from "@/components/ui";
import type { Campaign, OutreachRequest } from "@/lib/types";

export default function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<Campaign>(`/api/v1/campaigns/${id}`)
      .then(setCampaign)
      .catch((err) => setError(err instanceof ApiError ? String(err.detail) : "Failed to load"));
  }, [id]);

  const outreach = useApiList<OutreachRequest>(
    "/api/v1/outreach",
    { campaign_id: id, limit: 100 },
    [id]
  );

  if (error && !campaign) return <ErrorBanner message={error} />;
  if (!campaign) return <Spinner />;

  return (
    <div>
      <PageHeader title={campaign.name} description={campaign.description ?? undefined} />

      <Card className="mb-6">
        <h2 className="mb-3 text-sm font-semibold text-slate-700">Policy</h2>
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <Row label="Status"><Badge value={campaign.status} /></Row>
          <Row label="Channel">{campaign.channel}</Row>
          <Row label="Dry-run">{campaign.policy?.dry_run ? "yes" : "no"}</Row>
          <Row label="Min score">{campaign.policy?.min_lead_score ?? "—"}</Row>
          <Row label="Requires qualification">
            {campaign.policy?.require_qualification ? "yes" : "no"}
          </Row>
          <Row label="Requires evidence">{campaign.policy?.require_evidence ? "yes" : "no"}</Row>
          <Row label="Max/day">{campaign.policy?.max_contact_per_day ?? "—"}</Row>
        </dl>
      </Card>

      <h2 className="mb-2 text-sm font-semibold text-slate-700">Outreach requests</h2>
      {outreach.loading && <Spinner />}
      {outreach.data && outreach.data.length > 0 && (
        <Table columns={["Channel", "Status", "Scheduled", "Sent", "Provider message"]}>
          {outreach.data.map((o) => (
            <tr key={o.id} className="hover:bg-slate-50">
              <td className="px-4 py-2">{o.channel}</td>
              <td className="px-4 py-2">
                <Badge value={o.status} />
              </td>
              <td className="px-4 py-2 text-slate-500">
                {o.scheduled_at ? new Date(o.scheduled_at).toLocaleString() : "—"}
              </td>
              <td className="px-4 py-2 text-slate-500">
                {o.sent_at ? new Date(o.sent_at).toLocaleString() : "—"}
              </td>
              <td className="px-4 py-2 text-slate-500">{o.provider_message_id ?? "—"}</td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-slate-500">{label}</dt>
      <dd className="font-medium">{children}</dd>
    </div>
  );
}
