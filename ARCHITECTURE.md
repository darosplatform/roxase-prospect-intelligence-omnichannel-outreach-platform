# ROXASE — Architecture Document

**Prospect Intelligence & Omnichannel Outreach Platform**

> **ROXASE** is a SaaS platform for commercial intelligence, prospect discovery, lead scoring, CRM, and multi-channel outreach (Email, WhatsApp, Telegram, Meta). It is an independent project and has no relation to DAROS.

---

## 1. Overview & Vision

ROXASE exists to transform scattered public and private data into **actionable commercial intelligence**. The platform discovers companies and contacts, observes signals (hiring, funding, tech adoption, partnerships), enriches and validates the data through an evidence-first pipeline, qualifies prospects through AI-assisted scoring, and orchestrates multi-channel outreach — all within a secure, multi-tenant environment with full provenance tracking.

**Key differentiators:**

- **Evidence before conclusion.** No data point reaches a user or a campaign without an auditable trail.
- **AI-assisted, never AI-alone.** Models accelerate extraction, classification, and scoring; humans define policy and review exceptions.
- **Channel-native outreach.** First-class support for Email, WhatsApp Business, Telegram, and Meta — not bolted-on integrations.
- **Tenant-first security.** Every query, every record, every event is scoped to a workspace. Zero inter-tenant data leakage by construction.

---

## 2. Core Principle — Evidence Before Conclusion

Every piece of intelligence in ROXASE follows a single pipeline:

```
Observed Data → Source → Evidence → Normalization → Enrichment → AI Analysis → Qualification → Score → Business Action
```

| Stage | Responsibility |
|---|---|
| **Observed Data** | Raw artifact ingested from a source (HTML, API response, CSV row, webhook payload). |
| **Source** | Who/what produced it, when, from where, under what conditions. |
| **Evidence** | A normalized evidence record linking data ↔ source with confidence and validity window. |
| **Normalization** | Schema mapping, deduplication, entity resolution. |
| **Enrichment** | Supplementary data from third-party providers or internal knowledge bases. |
| **AI Analysis** | Classification, extraction, summarization — always logged with model + prompt version. |
| **Qualification** | Business rules determine whether the prospect fits an ideal profile. |
| **Score** | A numeric lead score with explainable factors and confidence bounds. |
| **Business Action** | CRM update, campaign trigger, alert, or manual review task. |

Nothing skips a stage. Nothing becomes "fact" without evidence.

---

## 3. Logical Architecture — 23 Functional Domains

ROXASE is organized into 23 functional domains. Each domain has clear boundaries, owns its data, and communicates with others through well-defined events and APIs.

### 3.1 Identity & Access Management (IAM)

- User registration, authentication (email/password, OAuth, SSO/SAML).
- JWT-based session tokens with short TTL and refresh rotation.
- RBAC: roles (Owner, Admin, Manager, Analyst, Operator, Viewer) mapped to granular permissions.
- API key management for programmatic access.
- MFA enforcement policies per workspace.

### 3.2 Workspace / Tenant Management

- Tenant = billing account. Workspace = operational container within a tenant.
- Workspace settings: name, timezone, locale, default currency, feature flags.
- Seat management, invitation flows, deactivation.
- Tenant-level configuration and secrets isolation.

### 3.3 Targeting

- Definition of ideal customer profiles (ICPs): firmographics, technographics, geo, signals.
- Segment builder: combinable filters (AND/OR) across company, contact, and signal attributes.
- Saved targets and target snapshots for reproducibility.
- Target-to-campaign linking.

### 3.4 Discovery

- Prospecting engine: crawlers, search aggregation, directory parsing, file import.
- Configurable discovery jobs per target/segment.
- Job scheduling (cron-like), concurrency control, and backoff.
- Raw ingestion storage with source metadata.
- Discovery result → Evidence pipeline handoff.

### 3.5 Source Management

- Registry of data sources: type (crawler, API, directory, manual), reliability rating, refresh cadence.
- Source health monitoring and automatic deprioritization on failure.
- API credential vault for paid data sources (not stored in code).
- Cost tracking per source (API credits, requests).

### 3.6 Company Intelligence

- Canonical company entity: identity, legal_name, display_name, domains, websites, locations, countries, sectors, size (employee range), description, technologies, social_profiles.
- Company timeline: discovered_at, enriched_at, updated_at, last_signal_at.
- Relationship graph: subsidiaries, competitors, partners, investors.
- Multi-source reconciliation: dedup by domain, legal name, registration ID.

### 3.7 Contact Intelligence

- Contact entity with rich status fields:
  - `source` — origin system or source ID.
  - `date_observation` — when the contact was first observed.
  - `confidence` — 0.0–1.0 based on source reliability and validation.
  - `validation_status` — UNVALIDATED | VALID | INVALID | STALE.
  - `contactability_status` — UNKNOWN | REACHABLE | UNREACHABLE | RESTRICTED.
  - `opt_out_status` — OPTED_IN | OPTED_OUT | NOT_APPLICABLE.
  - `do_not_contact_status` — CLEAR | DNC_GLOBAL | DNC_CHANNEL | DNC_WORKSPACE.
  - `provenance` — full evidence chain.
- Role/title classification (AI-assisted).
- Employment timeline and company association history.

### 3.8 Signal Intelligence

- Signal entity:
  - `id`, `company_id`, `type` (HIRING, FUNDING, TECH_ADOPTION, PARTNERSHIP, LEADERSHIP_CHANGE, PRODUCT_LAUNCH, REGULATORY, etc.), `source`, `source_url`, `observed_at`, `confidence`, `summary`, `evidence`, `expires_at`, `status`.
- Signal clustering: multiple raw observations → single business signal.
- Signal decay: automatic status transition (ACTIVE → STALE → EXPIRED).
- Signal → Campaign trigger rules.

### 3.9 Data Enrichment

- Normalization pipeline: name casing, address standardization, industry code mapping (SIC/NAICS), currency normalization.
- Entity resolution: fuzzy matching, dedup across sources, merge strategies.
- Enrichment providers: tech stack (BuiltWith/Wappalyzer-style), firmographics (Clearbit-style), social profile resolution.
- Confidence scoring per field based on source reliability and cross-validation.

### 3.10 Qualification

- Rule engine evaluating prospects against targeting criteria.
- Qualification statuses: QUALIFIED, PARTIALLY_QUALIFIED, UNQUALIFIED, PENDING_REVIEW.
- Qualification factors with weights and explanations.
- Human-in-the-loop: override capability with mandatory justification.

### 3.11 Lead Scoring

- Scoring output:
  - `total` — composite score (0–100).
  - `factors[]` — weighted contributing signals (e.g., "tech_fit: 15", "funding_recency: 12", "engagement: 8").
  - `explanations[]` — human-readable reason for each factor.
  - `confidence` — 0.0–1.0.
  - `scoring_version` — model/policy version for reproducibility.
  - `calculated_at` — timestamp.
- Configurable scoring models per workspace (rules-based, ML-assisted, or hybrid).
- Score decay over time without new evidence.

### 3.12 CRM

- Core entities: Company, Contact, Lead, Opportunity, Activity, Task, Note.
- Pipeline stages configurable per workspace.
- Activity timeline: calls, emails, meetings, notes, system events.
- Task assignment with due dates and reminders.
- Custom fields per entity type.
- Import/export with mapping.

### 3.13 Campaign Management

- Campaign definition: name, target segment, channel mix, message template, scheduling, budget.
- Campaign → Audience: dynamic or snapshot-based audience resolution.
- Campaign states: DRAFT | SCHEDULED | ACTIVE | PAUSED | COMPLETED | CANCELLED.
- A/B/n variant support for messages and timing.
- Campaign-level metrics and reporting.

### 3.14 Outreach

- Message orchestration: campaign → policy check → template render → channel dispatch → delivery tracking.
- Message states: DRAFT | QUEUED | DISPATCHED | SENT | DELIVERED | READ | REPLIED | BOUNCED | FAILED | OPTED_OUT.
- Throttling and send-window enforcement per channel and workspace.
- Reply-to routing: inbound messages → conversation thread → CRM activity.

### 3.15 Channel Integrations

- **Email:** SMTP/ESPs (SendGrid, Amazon SES, Mailgun), DKIM/SPF/DMARC verification, bounce/complaint webhooks.
- **WhatsApp Business API:** Official Cloud API, template pre-approval, media messages, interactive messages.
- **Telegram:** Bot API, inline keyboards, group/channel messaging.
- **Meta (Messenger):** Messenger Platform, persistent menu, structured messages.
- Channel adapter abstraction: uniform dispatch/receive interface regardless of provider.
- Per-channel rate limits, compliance rules, and opt-out handling.

### 3.16 Conversation Intelligence

- Thread management across channels (unified conversation view).
- Intent classification (interested, not interested, follow-up, objection, out-of-office).
- Sentiment analysis per message and per thread.
- Auto-draft responses with AI, requiring human approval before sending.
- Conversation → CRM activity sync.

### 3.17 AI Engine

- Central AI service providing:
  - Text classification (intent, topic, sentiment).
  - Named entity extraction.
  - Summarization (signal summaries, conversation summaries).
  - Entity resolution (matching across sources).
  - Qualification scoring assistance.
  - Lead scoring model inference.
  - Message draft generation.
- Observable, versioned, traceable, replaceable (see §10).
- Model-agnostic: supports multiple LLM providers with fallback routing.

### 3.18 Policy Engine

- Central gatekeeper for all outbound actions (see §11).
- Rule categories: prospect status, DNC, opt-out, frequency caps, channel rules, campaign rules, template compliance, regulatory limits.
- Evaluation modes: ALLOW, BLOCK, REVIEW, DRY_RUN.
- Policy versioning and audit of every decision.

### 3.19 Evidence & Provenance

- Evidence record structure (see §12):
  - source_id, source_url, observed_at, obtained_by, confidence, is_observed_vs_generated, validity_window, usage_permissions.
- Every data point in the system traces back to at least one evidence record.
- Evidence expiry and re-validation.
- Exportable provenance chains for compliance and audit.

### 3.20 Analytics

- Dashboard metrics: pipeline velocity, campaign performance, source ROI, team productivity.
- Funnel analytics: discovery → qualification → score → CRM → opportunity → revenue.
- Source effectiveness: cost per lead, conversion rate by source.
- Channel performance: open rates, reply rates, conversion by channel.
- Custom report builder with scheduled delivery.

### 3.21 Notifications

- In-app notifications (bell icon, notification center).
- Email notifications for critical events (campaign completion, high-score lead, DNC violation).
- Webhook notifications for external system integration.
- User-configurable notification preferences per event type.

### 3.22 Audit

- Immutable audit log for all state-changing actions.
- Logged fields: actor_id, actor_role, workspace_id, action, entity_type, entity_id, before_state, after_state, timestamp, ip, user_agent.
- Retention policy configurable per tenant (minimum 1 year).
- Exportable for compliance (GDPR, CCPA, SOC 2).

### 3.23 Administration

- Platform admin console (internal ROXASE team).
- Tenant provisioning and lifecycle management.
- Feature flag management.
- Global rate limits and abuse prevention.
- System health dashboard.
- Maintenance mode and deployment controls.

---

## 4. Physical Architecture — Docker-Based Infrastructure

### 4.1 Deployment Topology

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Docker Compose / Swarm                      │
│                                                                      │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────────┐   │
│  │  nginx   │───▶│   apps/api   │───▶│     services/discovery    │   │
│  │ (reverse │    │  (API layer) │    │  services/enrichment      │   │
│  │  proxy)  │    │              │    │  services/scoring          │   │
│  └──────────┘    └──────┬───────┘    │  services/outreach        │   │
│       │                 │            │  services/ai               │   │
│       │                 │            │  services/crawler          │   │
│       │                 ▼            └────────────┬───────────────┘   │
│       │          ┌──────────────┐                 │                   │
│       │          │  PostgreSQL  │◀────────────────┘                   │
│       │          └──────────────┘                                     │
│       │          ┌──────────────┐                                     │
│       │          │    Redis     │                                     │
│       │          └──────────────┘                                     │
│       │                                                               │
│       ▼          ┌──────────────┐                                     │
│  ┌──────────┐    │  apps/web    │                                     │
│  │ (static) │    │ (Next.js SSR)│                                     │
│  └──────────┘    └──────────────┘                                     │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.2 Component Specifications

| Component | Technology | Purpose |
|---|---|---|
| **Reverse Proxy** | nginx | TLS termination, rate limiting, static asset serving, request routing. |
| **API Backend** | Node.js / TypeScript (Fastify) | REST + WebSocket API gateway. Request validation, auth, routing to services. |
| **Services** | Node.js / TypeScript | Discrete bounded-context workers (discovery, enrichment, scoring, outreach, AI, crawler). |
| **Crawler Sandbox** | Node.js (isolated container) | Isolated execution environment for untrusted crawler scripts. Network-restricted. |
| **Database** | PostgreSQL 16+ | Primary data store. JSONB for flexible attributes, full-text search, row-level security for tenant isolation. |
| **Cache / Queue** | Redis 7+ | Session cache, job queues (BullMQ), rate limiting, pub/sub for real-time events. |
| **Frontend** | Next.js 14+ (React, TypeScript) | SSR/CSR hybrid SPA. Dashboard, CRM views, campaign builder, analytics. |
| **Object Storage** | S3-compatible (MinIO self-hosted or cloud) | Evidence artifacts, exported reports, uploaded files (CSV, contact lists). |

### 4.3 Why Node.js / TypeScript

- **Unified language** across API, workers, and crawler — shared types, shared validation, shared utilities.
- **Async-native** — excellent fit for I/O-heavy workloads (HTTP requests, database queries, message dispatch).
- **Type safety** — TypeScript enforces contracts between modules at compile time.
- **Ecosystem** — mature libraries for HTTP (Fastify), queues (BullMQ), validation (Zod), ORM (Drizzle/Kysely).
- **Monorepo friendly** — Turborepo or Nx for build orchestration across apps and packages.

### 4.4 Observability

| Pillar | Implementation |
|---|---|
| **Structured Logging** | JSON logs via `pino`. Fields: timestamp, level, service, trace_id, span_id, tenant_id, user_id, message. |
| **Metrics** | Prometheus-compatible metrics endpoint per service. Key metrics: request latency, error rate, queue depth, job duration, channel delivery rate. |
| **Distributed Tracing** | OpenTelemetry SDK. Trace context propagated across services via headers and message metadata. |
| **Health Checks** | `/healthz` (liveness) and `/readyz` (readiness) endpoints per container. Dependencies checked: database, Redis, external APIs. |
| **Alerting** | Prometheus → Alertmanager → Slack/PagerDuty. Alert rules for: error rate spike, queue backlog, disk usage, certificate expiry, crawler failures. |

---

## 5. Data Architecture — Entity Models

### 5.1 Company

```
Company
├── id                    UUID (PK)
├── tenant_id             UUID (FK → Tenant)
├── legal_name            TEXT
├── display_name          TEXT
├── domains               TEXT[]
├── websites              JSONB          [{url, type, verified}]
├── locations             JSONB          [{address, city, state, country, postal_code, type}]
├── countries             TEXT[]         [ISO 3166-1 alpha-2]
├── sectors               JSONB          [{code, label, source}]
├── size                  JSONB          {min, max, unit}   (employees)
├── description           TEXT
├── technologies          JSONB          [{name, category, confidence}]
├── social_profiles       JSONB          [{platform, url, handle}]
├── founded_year          INT
├── revenue_range         JSONB          {min, max, currency}
├── tags                  TEXT[]
├── custom_fields         JSONB
├── discovered_at         TIMESTAMPTZ
├── enriched_at           TIMESTAMPTZ
├── updated_at            TIMESTAMPTZ
├── status                ENUM (ACTIVE, INACTIVE, MERGED, DELETED)
└── merged_into_id        UUID (FK → Company, nullable)
```

### 5.2 Contact

```
Contact
├── id                    UUID (PK)
├── tenant_id             UUID (FK → Tenant)
├── company_id            UUID (FK → Company, nullable)
├── source                TEXT              (origin system/source ID)
├── date_observation       TIMESTAMPTZ       (first seen)
├── confidence            DECIMAL(3,2)      (0.00–1.00)
├── validation_status     ENUM (UNVALIDATED, VALID, INVALID, STALE)
├── contactability_status ENUM (UNKNOWN, REACHABLE, UNREACHABLE, RESTRICTED)
├── opt_out_status        ENUM (OPTED_IN, OPTED_OUT, NOT_APPLICABLE)
├── do_not_contact_status ENUM (CLEAR, DNC_GLOBAL, DNC_CHANNEL, DNC_WORKSPACE)
├── first_name            TEXT
├── last_name             TEXT
├── email                 TEXT
├── phone                 TEXT
├── title                 TEXT
├── role_level            ENUM (C_LEVEL, VP, DIRECTOR, MANAGER, INDIVIDUAL, UNKNOWN)
├── linkedin_url          TEXT
├── social_profiles       JSONB
├── custom_fields         JSONB
├── tags                  TEXT[]
├── provenance            JSONB            (→ Evidence chain)
├── created_at            TIMESTAMPTZ
├── updated_at            TIMESTAMPTZ
└── deleted_at            TIMESTAMPTZ      (soft delete)
```

### 5.3 Signal

```
Signal
├── id                    UUID (PK)
├── tenant_id             UUID (FK → Tenant)
├── company_id            UUID (FK → Company)
├── type                  ENUM (HIRING, FUNDING, TECH_ADOPTION, PARTNERSHIP,
│                               LEADERSHIP_CHANGE, PRODUCT_LAUNCH, REGULATORY,
│                               M&A, EXPANSION, RETRENCHMENT, OTHER)
├── source                TEXT
├── source_url            TEXT
├── observed_at           TIMESTAMPTZ
├── confidence            DECIMAL(3,2)
├── summary               TEXT
├── evidence              JSONB            (raw + normalized data)
├── expires_at            TIMESTAMPTZ
├── status                ENUM (ACTIVE, STALE, EXPIRED, ARCHIVED)
├── created_at            TIMESTAMPTZ
└── updated_at            TIMESTAMPTZ
```

### 5.4 Lead Score

```
LeadScore
├── id                    UUID (PK)
├── tenant_id             UUID (FK → Tenant)
├── entity_type           ENUM (COMPANY, CONTACT)
├── entity_id             UUID
├── total                 INT              (0–100)
├── factors               JSONB            [{key, value, weight, label}]
├── explanations          JSONB            [{factor, reasoning, evidence_ids}]
├── confidence            DECIMAL(3,2)
├── scoring_version       TEXT             (model/policy version identifier)
├── calculated_at         TIMESTAMPTZ
├── expires_at            TIMESTAMPTZ
├── created_at            TIMESTAMPTZ
└── updated_at            TIMESTAMPTZ
```

### 5.5 CRM Entities

```
Lead
├── id, tenant_id, company_id, contact_id
├── stage (NEW, CONTACTED, QUALIFIED, PROPOSAL, NEGOTIATION, WON, LOST, DISQUALIFIED)
├── source_campaign_id, assigned_to, score_id
├── created_at, updated_at

Opportunity
├── id, tenant_id, company_id, contact_id, lead_id
├── name, value, currency, stage, expected_close_date
├── assigned_to, probability
├── created_at, updated_at

Activity
├── id, tenant_id, entity_type, entity_id
├── type (EMAIL, CALL, MEETING, NOTE, SYSTEM, SIGNAL)
├── direction (INBOUND, OUTBOUND, INTERNAL)
├── subject, body, metadata
├── performed_by, performed_at

Task
├── id, tenant_id, entity_type, entity_id
├── title, description, due_date, assigned_to
├── status (OPEN, IN_PROGRESS, COMPLETED, CANCELLED)

Note
├── id, tenant_id, entity_type, entity_id
├── content, author_id, visibility
├── created_at, updated_at

Campaign          (→ §3.13)
Conversation      (→ §3.16)
Message           (→ §3.14)
```

### 5.6 Data Lifecycle

Every business entity follows a defined lifecycle:

```
DISCOVERED → VALIDATED → ACTIVE → STALE → EXPIRED → DELETED
```

| Transition | Trigger | Example |
|---|---|---|
| DISCOVERED → VALIDATED | Enrichment pipeline confirms data, cross-references sources. | Contact email verified, company domain confirmed. |
| VALIDATED → ACTIVE | Qualification passes, entity enters CRM or campaign scope. | Contact meets ICP criteria, assigned to outreach list. |
| ACTIVE → STALE | No new evidence within configurable TTL (e.g., 90 days). | No signal updates, no engagement, email bounces. |
| STALE → EXPIRED | Beyond staleness threshold (e.g., 180 days). | Contact information likely outdated. |
| EXPIRED → DELETED | Retention policy expires, or manual purge. | GDPR right-to-erasure request fulfilled. |

Soft-delete is used throughout; hard delete only on retention expiry or explicit compliance request.

---

## 6. Module Architecture — Service Boundaries

### 6.1 Monorepo Structure

```
roxase/
├── apps/
│   ├── web/                    # Next.js frontend
│   └── api/                    # API gateway / backend (Fastify)
├── services/
│   ├── discovery/              # Crawling, search, directory parsing
│   ├── enrichment/             # Data normalization, entity resolution, dedup
│   ├── scoring/                # Lead scoring engine
│   ├── outreach/               # Message orchestration, channel dispatch
│   ├── ai/                     # AI inference service
│   └── crawler/                # Isolated crawler sandbox
├── packages/
│   ├── shared/                 # Utilities, helpers, constants
│   ├── types/                  # Shared TypeScript types and interfaces
│   ├── config/                 # Environment and service configuration
│   ├── logger/                 # Structured logging (pino wrapper)
│   ├── policy/                 # Policy engine (rules, evaluation, audit)
│   └── evidence/               # Evidence creation, validation, chain management
├── infrastructure/
│   ├── docker/                 # Dockerfiles, docker-compose
│   ├── nginx/                  # Reverse proxy config
│   └── migrations/             # Database migrations
├── scripts/                    # Dev, CI/CD, seed data scripts
├── tests/                      # Integration and unit tests
├── e2e/                        # End-to-end tests
├── integration/                # External integration configs
├── integrations/               # Channel adapter implementations
└── governance/                 # Compliance, policies, data governance
```

### 6.2 Service Responsibilities

| Service | Bounded Context | Interfaces |
|---|---|---|
| **apps/web** | User-facing SPA. Renders dashboards, CRM, campaign builder, analytics. | Consumes REST + WebSocket APIs. |
| **apps/api** | API gateway. Authentication, rate limiting, request routing, response formatting. | Exposes REST + WebSocket to frontend. Publishes events to Redis. |
| **services/discovery** | Prospect discovery. Manages crawlers, search queries, directory imports, file uploads. | Consumes discovery jobs from queue. Publishes `CompanyDiscovered`, `ContactDiscovered`. |
| **services/enrichment** | Data normalization, deduplication, entity resolution, enrichment API calls. | Consumes raw discovered data. Publishes enriched entities with evidence. |
| **services/scoring** | Lead scoring. Rules engine + ML model inference. | Consumes scoring requests. Publishes `LeadScored`. |
| **services/outreach** | Message orchestration. Template rendering, policy checking, channel dispatch, delivery tracking. | Consumes `MessageRequested` events. Publishes `MessageSent`, `MessageReceived`. |
| **services/ai** | AI inference. Classification, extraction, summarization, entity resolution, draft generation. | Consumed by other services via internal API. Logs all calls with model/prompt version. |
| **services/crawler** | Isolated sandbox for executing untrusted crawler scripts. Network-restricted, resource-limited. | Runs in separate container. Communicates via message queue only. |

### 6.3 Shared Packages

| Package | Purpose |
|---|---|
| **packages/shared** | Date utilities, string normalization, ID generation, error classes, retry logic. |
| **packages/types** | TypeScript interfaces and enums for all domain entities, events, API contracts. Single source of truth. |
| **packages/config** | Environment variable loading, service configuration, feature flags. Uses `zod` for validation. |
| **packages/logger** | `pino`-based structured logger with correlation ID injection, tenant context, and redaction of sensitive fields. |
| **packages/policy** | Policy rule definitions, evaluation engine, decision audit. Consumed by outreach and CRM services. |
| **packages/evidence** | Evidence record creation, validation, expiry checking, provenance chain traversal. |

---

## 7. Main Flows

### 7.1 Discovery → Intelligence → CRM

```
┌────────────┐     ┌──────────────┐     ┌────────────┐     ┌───────────┐
│  Discovery  │────▶│  Enrichment  │────▶│  Evidence   │────▶│  Scoring   │
│  (raw data) │     │ (normalize,  │     │  (provenance│     │ (lead      │
│             │     │  resolve,    │     │   chain)    │     │  scoring)  │
│             │     │  dedup)      │     │             │     │            │
└────────────┘     └──────────────┘     └────────────┘     └─────┬─────┘
                                                                 │
                   ┌──────────────┐     ┌────────────┐          │
                   │     CRM      │◀────│ Qualification│◀────────┘
                   │  (Lead/      │     │ (ICP match, │
                   │  Opportunity)│     │  rules)     │
                   └──────────────┘     └────────────┘
```

**Steps:**
1. Discovery service crawls, searches, or imports raw data → stores with source metadata.
2. Enrichment service normalizes, deduplicates, resolves entities, enriches from third-party sources.
3. Evidence records created linking every data point to its source, timestamp, and confidence.
4. Qualification service evaluates against workspace ICP criteria.
5. Scoring service calculates lead score with explainable factors.
6. Qualified leads with scores are pushed to CRM as Leads or enriched existing records.

### 7.2 Campaign → Outreach → Response → CRM

```
┌───────────┐     ┌───────────┐     ┌──────────┐     ┌──────────┐
│  Campaign  │────▶│  Policy   │────▶│ Outreach │────▶│ Channel  │
│  (target + │     │  Engine   │     │ (render  │     │ (Email/  │
│  template) │     │ (gate)    │     │  + send) │     │  WA/TG/  │
│            │     │           │     │          │     │  Meta)   │
└───────────┘     └───────────┘     └──────────┘     └────┬─────┘
                                                           │
                   ┌──────────────┐     ┌──────────┐      │
                   │  Conversation │◀────│ Delivery │◀─────┘
                   │  Intelligence │     │ Webhook  │
                   │  (intent,     │     │ (bounce, │
                   │   sentiment)  │     │  reply)  │
                   └──────┬───────┘     └──────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │  CRM Update  │
                   │  (Activity,  │
                   │   Lead stage)│
                   └──────────────┘
```

**Steps:**
1. Campaign defines audience (target segment), message templates, channel mix, and schedule.
2. For each recipient, Policy Engine evaluates: DNC status, opt-out, frequency cap, channel rules, compliance.
3. Outreach service renders template with personalization variables, dispatches to channel adapter.
4. Channel adapter sends via provider API (SendGrid, WhatsApp Cloud API, etc.).
5. Delivery webhooks update message status (sent, delivered, read, bounced, complained).
6. Inbound replies route through Conversation Intelligence for intent/sentiment classification.
7. Conversation thread and CRM Activity are updated automatically.

### 7.3 Signal Detection → Campaign Trigger

```
┌─────────────┐     ┌────────────┐     ┌─────────┐     ┌──────────┐
│   Signal     │────▶│  Evidence  │────▶│   CRM   │────▶│ Campaign │
│  Detection   │     │  (record)  │     │ (notify)│     │ Trigger  │
│ (crawler,    │     │            │     │         │     │ (auto or │
│  search)     │     │            │     │         │     │  review) │
└─────────────┘     └────────────┘     └─────────┘     └──────────┘
```

**Steps:**
1. Discovery/crawler detects a signal (e.g., target company announces funding).
2. Signal record created with evidence, source URL, confidence, and expiry.
3. CRM notifies assigned owner; signal appears on company timeline.
4. If auto-trigger rules are configured (e.g., "FUNDING signal on QUALIFIED company → create outreach campaign"), Campaign is created or appended to.

---

## 8. Event Model

All inter-service communication is event-driven via Redis pub/sub (or a message broker for production scaling).

### 8.1 Key Events

| Event | Publisher | Consumers | Payload Highlights |
|---|---|---|---|
| **CompanyDiscovered** | services/discovery | services/enrichment, CRM | company_id, source, raw_data |
| **ContactDiscovered** | services/discovery | services/enrichment, CRM | contact_id, company_id, source, raw_data |
| **SignalDetected** | services/discovery | CRM, Campaign, Analytics | signal_id, company_id, type, confidence |
| **LeadScored** | services/scoring | CRM, Campaign, Analytics | entity_id, score, factors, version |
| **CampaignCreated** | apps/api | services/outreach, Analytics | campaign_id, target_segment, channels |
| **MessageRequested** | services/outreach | services/outreach (dispatch) | message_id, channel, recipient, template |
| **MessageSent** | services/outreach | Analytics, CRM | message_id, channel, timestamp |
| **MessageReceived** | services/outreach (inbound webhook) | services/ai, CRM | message_id, thread_id, content |
| **ConversationUpdated** | services/ai | CRM, Analytics | conversation_id, intent, sentiment |
| **OptOutReceived** | services/outreach | Policy Engine, CRM | contact_id, channel, timestamp |

### 8.2 Event Envelope

```typescript
interface DomainEvent {
  id: string;                // Event ID (UUID)
  type: string;              // Event type (e.g., "CompanyDiscovered")
  tenant_id: string;         // Tenant scope
  workspace_id: string;      // Workspace scope
  timestamp: string;         // ISO 8601
  source: string;            // Publishing service
  correlation_id: string;    // Trace ID for distributed tracing
  payload: Record<string, unknown>;
  metadata?: Record<string, unknown>;  // Optional: model version, prompt version, etc.
}
```

---

## 9. Security Architecture

### 9.1 Network Isolation

- **Crawler sandbox** runs in a network-restricted container. No outbound internet access except through a controlled proxy with allowlisted domains. No access to internal services except via message queue.
- **Inter-service communication** uses internal Docker network. No service exposed to the public internet except nginx (reverse proxy).
- **Database access** restricted to API and relevant worker services only. No direct DB access from frontend or crawler.

### 9.2 Tenant Isolation

- Every table includes `tenant_id` column.
- Row-Level Security (RLS) policies in PostgreSQL enforce tenant scoping at the database level — application-level checks are a defense-in-depth layer, not the primary mechanism.
- All queries are scoped by `tenant_id` extracted from the authenticated JWT.
- Redis keys are namespaced by tenant: `tenant:{id}:*`.

### 9.3 Authentication & Authorization

- **Authentication:** JWT with short-lived access tokens (15 min) and refresh tokens (7 days). Refresh rotation on every use.
- **Authorization:** RBAC model. Roles: Owner, Admin, Manager, Analyst, Operator, Viewer. Permissions are granular (e.g., `campaign:create`, `contact:read`, `signal:export`).
- **API Keys:** Generated per workspace for programmatic access. Scoped permissions, rotation support, usage logging.

### 9.4 Secrets Management

- No secrets in version control. `.env` files are gitignored.
- `.env.example` committed with placeholder values for developer reference.
- Production secrets managed via environment variables injected at runtime (Docker secrets, cloud secret managers).
- API credentials for third-party services (email providers, WhatsApp API) stored encrypted in the database, accessible only by the outreach service.

### 9.5 Input Validation

- All API inputs validated using `zod` schemas at the API gateway.
- SQL injection prevented by parameterized queries (never string concatenation).
- XSS prevention: output encoding on frontend, Content-Security-Policy headers.
- File upload validation: type checking, size limits, virus scanning for imports.

### 9.6 SSRF Protection

- All outbound HTTP requests from services validated against an allowlist of target domains.
- Crawler sandbox has additional restrictions: no internal IP ranges, no metadata endpoints, no `.local` domains.
- Redirect following limited to same-domain or explicitly allowed domains.

### 9.7 Prompt Injection Defense

- AI inputs are sanitized and bounded. User-supplied content is wrapped in structured prompts with clear delimiters.
- AI output is never trusted as factual — it goes through the evidence pipeline before becoming a data point.
- System prompts are not modifiable by user input. User content is treated as data, not instructions.
- Output filtering for sensitive patterns (emails, phone numbers, API keys) before display.

### 9.8 Webhook Verification

- All inbound webhooks (delivery status, payment, OAuth callbacks) verified via:
  - HMAC signature validation (provider-specific).
  - Timestamp freshness check (reject stale webhooks).
  - IP allowlisting where provider publishes IPs.
- Invalid webhooks logged, rejected, and counted for abuse detection.

### 9.9 Rate Limiting

- **Global:** nginx-level rate limiting per IP (e.g., 100 req/min for unauthenticated, 1000 req/min for authenticated).
- **Per-tenant:** Application-level rate limiting (configurable per plan tier).
- **Per-channel:** Outreach service enforces per-channel send limits (e.g., WhatsApp: 100 messages/second per number).
- Rate limit headers (`X-RateLimit-*`) returned to clients.

### 9.10 Audit Logging

- Every state-changing action logged to an immutable audit table.
- Fields: `actor_id`, `actor_role`, `tenant_id`, `workspace_id`, `action`, `entity_type`, `entity_id`, `before_state`, `after_state`, `timestamp`, `ip`, `user_agent`.
- Audit logs are append-only. No update or delete operations permitted.
- Retention: minimum 1 year, configurable per tenant.
- Exportable in CSV/JSON for compliance reviews.

---

## 10. AI Engine Architecture

The AI Engine is a dedicated service that provides machine learning and LLM-based capabilities to the rest of the platform.

### 10.1 Design Principles

| Principle | Implementation |
|---|---|
| **Observable** | Every AI call is logged with full context (see §10.2). |
| **Versioned** | Model version, prompt version, and configuration version are recorded per call. |
| **Traceable** | Input reference, output, confidence, and latency are stored for every inference. |
| **Replaceable** | Model-agnostic interface. Swapping providers (OpenAI, Anthropic, open-source) requires only adapter changes. |
| **Policy-bounded** | AI output is subject to the Policy Engine before becoming actionable. |

### 10.2 Mandatory Logging

Every AI inference call must log:

```typescript
interface AICallLog {
  id: string;                  // Unique call ID
  service: string;             // Calling service (e.g., "enrichment", "scoring")
  model: string;               // Model name (e.g., "gpt-4o", "claude-sonnet-4-20250514")
  model_version: string;       // Model version/variant
  prompt_version: string;      // Prompt template version
  input_reference: string;     // Reference to input data (entity ID, not full payload)
  output_summary: string;      // Truncated output for audit
  confidence: number;          // Model-reported confidence
  latency_ms: number;          // Response time
  tokens_in: number;           // Input tokens
  tokens_out: number;          // Output tokens
  cost_usd: number;            // Estimated cost
  created_at: string;          // ISO 8601
  workspace_id: string;        // Tenant scope
}
```

### 10.3 Critical Rule

> **AI output must never become factual data without verification.**

All AI-generated content is classified as **unverified evidence**. It enters the system with `is_observed_vs_generated: false` and a lower confidence score. It must pass through the enrichment/validation pipeline (cross-referencing with other sources, human review, or policy rules) before being promoted to verified data.

### 10.4 Capabilities

| Capability | Input | Output | Used By |
|---|---|---|---|
| Classification | Text (email, message, webpage) | Category, confidence | Conversation Intelligence, Enrichment |
| Entity Extraction | Unstructured text | Structured entities (companies, people, events) | Discovery, Enrichment |
| Summarization | Long text (article, conversation) | Concise summary | Signal Intelligence, Conversation Intelligence |
| Entity Resolution | Multiple candidate records | Match score + merged entity | Enrichment |
| Lead Scoring Assistance | Company + contact + signals | Score factors + explanations | Scoring |
| Message Draft Generation | Context + template + personalization variables | Draft message | Outreach, Conversation Intelligence |

### 10.5 Fallback Strategy

- Primary model configured per workspace (configurable by admin).
- Fallback chain: primary → secondary → local/open-source model.
- If all models fail, the operation is queued for retry and the workspace is notified.
- AI-dependent features degrade gracefully: scoring falls back to rules-only mode, drafts are not generated but manual composition is available.

---

## 11. Policy Engine

The Policy Engine is the central gatekeeper for all outbound and state-changing business actions.

### 11.1 Scope

All outreach must pass through the Policy Engine **before** dispatch. This includes:
- Email sends
- WhatsApp messages
- Telegram messages
- Meta Messenger messages
- Any automated CRM state changes triggered by campaigns

### 11.2 Rule Categories

| Category | Examples |
|---|---|
| **Prospect Status** | Is the contact qualified? Is the company active? |
| **Do-Not-Contact** | DNC_GLOBAL (regulatory), DNC_CHANNEL (channel-specific), DNC_WORKSPACE (workspace-level block). |
| **Opt-Out** | Has the contact opted out of this channel or all channels? |
| **Frequency** | How many messages sent in the last 24h/7d/30d? Is the contact over-messaged? |
| **Channel Rules** | WhatsApp: template required for first message. Email: SPF/DKIM configured? Telegram: bot not blocked? |
| **Campaign Rules** | Campaign is ACTIVE? Recipient is in audience? Send window is open? |
| **Template Compliance** | Template approved? Personalization variables filled? No prohibited content? |
| **Limits** | Daily send limit per workspace? Per-channel quota? Budget remaining? |
| **Compliance** | GDPR consent check? CCPA opt-out? Regional regulations? |

### 11.3 Evaluation Modes

| Mode | Behavior |
|---|---|
| **ALLOW** | Policy check passed. Action proceeds. |
| **BLOCK** | Policy check failed. Action is prevented. Reason logged. Contact/task created for review if needed. |
| **REVIEW** | Ambiguous result. Action is held in a review queue for human decision. |
| **DRY_RUN** | Evaluation runs but no action is taken or blocked. Used for testing and simulation. |

### 11.4 Policy Decision Log

Every policy evaluation is logged:

```typescript
interface PolicyDecision {
  id: string;
  action_type: string;           // e.g., "send_email", "create_campaign"
  entity_type: string;           // e.g., "contact", "campaign"
  entity_id: string;
  tenant_id: string;
  workspace_id: string;
  rules_evaluated: string[];     // List of rule IDs checked
  result: "ALLOW" | "BLOCK" | "REVIEW" | "DRY_RUN";
  reason: string;                // Human-readable explanation
  blocked_by_rule?: string;      // If BLOCKED, which rule
  evaluated_at: string;
  context: Record<string, unknown>;  // Relevant context (DNC status, last message date, etc.)
}
```

---

## 12. Multi-Tenancy

### 12.1 Hierarchy

```
Tenant (billing account)
└── Workspace (operational container)
    └── User (with Role)
        └── Permission (granular access rights)
```

- A **Tenant** represents a billing account (company/organization).
- A **Workspace** is an operational unit within a tenant (e.g., "Sales - EMEA", "Marketing - APAC"). Each workspace has its own campaigns, CRM data, and settings.
- A **User** belongs to one or more workspaces with a specific role per workspace.
- **Roles** map to **Permissions** (RBAC). Permissions are fine-grained: `campaign:create`, `contact:read`, `signal:export`, `policy:override`.

### 12.2 Data Isolation

- Every business entity (Company, Contact, Signal, Lead, Campaign, etc.) carries a `tenant_id` column.
- PostgreSQL Row-Level Security (RLS) policies enforce tenant scoping: every query is automatically filtered by `tenant_id` from the authenticated JWT.
- Redis keys are namespaced: `tenant:{tenant_id}:workspace:{workspace_id}:*`.
- Object storage paths are prefixed: `{tenant_id}/{workspace_id}/...`.
- Crawler sandbox outputs are scoped to the requesting tenant.

### 12.3 Zero Inter-Tenant Data Leakage

- RLS is the **primary** isolation mechanism at the database level.
- Application-level `tenant_id` extraction and injection is a **defense-in-depth** layer.
- No cross-tenant joins are possible without explicit (and logged) admin override.
- Audit logs capture all access attempts, including any that touch RLS boundaries.
- Regular security testing includes inter-tenant access attempts as part of the test suite.

---

## 13. Evidence & Provenance

### 13.1 The Seven Questions

Every data point in ROXASE must answer:

| # | Question | Field |
|---|---|---|
| 1 | **Where did it come from?** | `source_id` — Registry entry identifying the data source. |
| 2 | **From what URL or document?** | `source_url` — Direct link to the original artifact. |
| 3 | **When was it observed?** | `observed_at` — Timestamp of the observation, not the ingestion. |
| 4 | **How was it obtained?** | `obtained_by` — Method: crawling, API call, manual entry, file import. |
| 5 | **How confident are we?** | `confidence` — 0.0–1.0, derived from source reliability + cross-validation. |
| 6 | **Is it observed or generated?** | `is_observed_vs_generated` — Raw data vs. AI-generated inference. |
| 7 | **Is it still valid and usable?** | `valid_from`, `valid_until`, `usage_permissions` — Validity window and usage rights. |

### 13.2 Evidence Record

```typescript
interface EvidenceRecord {
  id: string;
  tenant_id: string;
  source_id: string;              // FK → Source registry
  source_url: string;             // Direct link to raw artifact
  observed_at: string;            // When the data was first observed
  obtained_by: string;            // Method: "crawler", "api", "manual", "import"
  confidence: number;             // 0.0–1.0
  is_observed_vs_generated: boolean;
  validity_window: {
    valid_from: string;
    valid_until: string | null;   // null = no expiry defined
  };
  usage_permissions: {
    can_use_for_outreach: boolean;
    can_use_for_ai_training: boolean;
    requires_attribution: boolean;
  };
  data_reference: string;         // Reference to the actual data (not stored inline)
  created_at: string;
  updated_at: string;
}
```

### 13.3 Provenance Chain

- Every entity (Company, Contact, Signal, etc.) links to one or more Evidence Records.
- Evidence Records can reference each other (e.g., "this enrichment was triggered by this discovery evidence").
- Full provenance chains are traversable: given a Contact, you can trace back to every source that contributed to any field.
- Provenance chains are exportable for compliance (GDPR Article 15 — Right of Access).

### 13.4 Evidence Lifecycle

- Evidence records are **append-only**. New evidence is added; old evidence is never deleted (but can be marked superseded).
- Evidence validity is checked periodically. Expired evidence triggers re-validation or data staleness transition.
- When an entity is updated (e.g., contact email changed), both the old and new evidence records are retained.

---

*Document version: 1.0 — September 2026*
*ROXASE — Prospect Intelligence & Omnichannel Outreach Platform*
