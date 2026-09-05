// Mirrors backend Pydantic *Read schemas (app/schemas/*.py). Keep field
// names identical to the JSON the API actually returns — this file is not a
// separate source of truth, it's a typed reflection of one.

export type UUID = string;
export type ISODateTime = string;

export type Role = "owner" | "admin" | "manager" | "analyst" | "operator" | "viewer";

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface JwtPayload {
  sub: string;
  tenant_id: UUID;
  role: Role;
  exp: number;
  [key: string]: unknown;
}

export interface Company {
  id: UUID;
  tenant_id: UUID;
  legal_name: string;
  domain: string | null;
  country: string | null;
  industry: string | null;
  employee_count: number | null;
  source: string | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface Contact {
  id: UUID;
  tenant_id: UUID;
  company_id: UUID | null;
  first_name: string | null;
  last_name: string | null;
  job_title: string | null;
  email: string | null;
  phone: string | null;
  linkedin_url: string | null;
  source: string | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface Evidence {
  id: UUID;
  tenant_id: UUID;
  company_id: UUID | null;
  contact_id: UUID | null;
  lead_id: UUID | null;
  source_url: string;
  source_name: string | null;
  evidence_type: string | null;
  title: string | null;
  excerpt: string | null;
  content_hash: string | null;
  collected_at: ISODateTime;
  published_at: ISODateTime | null;
  confidence: number;
  metadata: Record<string, unknown> | null;
  created_at: ISODateTime;
}

export interface Signal {
  id: UUID;
  tenant_id: UUID;
  company_id: UUID;
  evidence_id: UUID | null;
  signal_type: string;
  title: string | null;
  description: string | null;
  source_url: string | null;
  source_name: string | null;
  detected_at: ISODateTime;
  confidence: number;
  status: string;
  fingerprint: string | null;
  deleted_at: ISODateTime | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface ScoreBreakdown {
  fit: number;
  intent: number;
  signal: number;
  data_confidence: number;
  freshness: number;
}

export interface ScoreFactor {
  name: string;
  impact: number;
  evidence_ids: UUID[];
}

export interface Lead {
  id: UUID;
  tenant_id: UUID;
  company_id: UUID | null;
  contact_id: UUID | null;
  score: number | null;
  status: string;
  qualification_reason: string | null;
  qualification_status: "unqualified" | "candidate" | "qualified" | "disqualified";
  qualified_at: ISODateTime | null;
  qualified_by: UUID | null;
  fit_score: number | null;
  intent_score: number | null;
  signal_score: number | null;
  data_confidence: number | null;
  freshness_score: number | null;
  scoring_version: string | null;
  score_explanation: { breakdown?: ScoreBreakdown; factors?: ScoreFactor[] } | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface CampaignPolicy {
  min_lead_score: number | null;
  min_confidence: number | null;
  min_evidence_freshness_days: number | null;
  allowed_channels: string[] | null;
  require_qualification: boolean;
  require_evidence: boolean;
  max_contact_per_day: number | null;
  dry_run: boolean;
}

export interface Campaign {
  id: UUID;
  tenant_id: UUID;
  name: string;
  description: string | null;
  status: string;
  channel: string;
  created_by: UUID | null;
  starts_at: ISODateTime | null;
  ends_at: ISODateTime | null;
  policy: CampaignPolicy | null;
  deleted_at: ISODateTime | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface OutreachRequest {
  id: UUID;
  tenant_id: UUID;
  campaign_id: UUID | null;
  lead_id: UUID | null;
  contact_id: UUID | null;
  template_id: UUID | null;
  policy_decision_id: UUID | null;
  channel: string;
  status: string;
  idempotency_key: string;
  scheduled_at: ISODateTime | null;
  sent_at: ISODateTime | null;
  provider_message_id: string | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface PolicyDecision {
  id: UUID;
  decision: "ALLOW" | "DENY" | "REVIEW";
  policy_version: string;
  reasons: { code: string; message?: string }[];
  evidence_ids: UUID[];
}

export interface DiscoveryJob {
  id: UUID;
  tenant_id: UUID;
  status: string;
  source_type: string;
  target: string;
  target_hash: string;
  requested_by: UUID | null;
  options: Record<string, unknown> | null;
  attempt_count: number;
  last_error: string | null;
  started_at: ISODateTime | null;
  finished_at: ISODateTime | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface DiscoverySource {
  id: UUID;
  tenant_id: UUID;
  job_id: UUID;
  url: string;
  url_hash: string;
  status: string;
  source_name: string | null;
  discovered_via: string | null;
  validation_status: string | null;
  rejection_reason: string | null;
  fetched_at: ISODateTime | null;
  http_status: number | null;
  content_hash: string | null;
  raw_size: number | null;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export interface ExtractionResult {
  company_id: UUID | null;
  contact_ids: UUID[];
  evidence_id: UUID | null;
  page_type: string;
  skipped_reason: string | null;
}

export interface AuditEvent {
  id: UUID;
  tenant_id: UUID;
  actor_user_id: UUID | null;
  action: string;
  entity_type: string;
  entity_id: UUID | null;
  metadata: Record<string, unknown> | null;
  created_at: ISODateTime;
}
