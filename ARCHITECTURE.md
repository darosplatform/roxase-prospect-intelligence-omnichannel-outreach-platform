# ROXASE — Architecture

**Prospect Intelligence & Omnichannel Outreach Platform**

> This document describes the system as it is actually implemented and running today. For the original pre-implementation design (Node.js/Fastify/microservices/BullMQ/MinIO — abandoned in favor of what follows), see [`docs/archive/INITIAL_ARCHITECTURE.md`](docs/archive/INITIAL_ARCHITECTURE.md).

---

## 1. Core principle — Evidence before conclusion

No data point reaches a Lead, a Score, or an outbound message without a traceable path back to where it came from. Every stage of the pipeline carries provenance forward instead of discarding it:

```
Discovery job
      v
Secure Fetch (SSRF-safe)
      v
RawDocument (server-computed hash, never client-supplied)
      v
Extraction / Normalization
      v
Evidence (source_url, confidence, provenance)
      v
Signal (keyword/type-classified, never fabricated)
      v
Lead
      v
Qualification (requires cited Evidence — never a bare score)
      v
Score (deterministic, versioned, explainable breakdown + factors)
      v
Campaign
      v
Policy Engine (ALLOW / DENY / REVIEW, versioned, reasoned)
      v
OutreachRequest
      v
Outbox / Worker (claim, lease, retry, backoff)
      v
Provider (Mock today; DRY_RUN sticky until a real channel is explicitly wired)
```

For any Lead, every one of these links is queryable: which URL produced which Evidence, which Evidence produced which Signal, which Signal fed which score factor, which Policy decision (with its reasons) gated which OutreachRequest.

## 2. Stack (as built, not as originally envisioned)

| Layer | Technology |
|---|---|
| Backend API | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x (async) |
| Database | PostgreSQL 16, Alembic migrations |
| Cache / rate limiting | Redis 7 |
| Background processing | Two independent asyncio polling workers (outreach outbox, discovery) — no queue broker |
| Frontend | Next.js 16, React 18, TypeScript, Tailwind |
| Testing | pytest (backend, 380+ tests), ESLint + `next build` (frontend) |
| Deployment | Docker Compose: postgres, redis, backend, worker, discovery-worker, frontend |

Deliberately **not** used: Celery, Kafka, Kubernetes, a queue broker, an ORM-agnostic microservice split, or any ML model for scoring/extraction. The system is a single FastAPI monolith plus two lightweight worker processes sharing the same database — sufficient for the actual throughput this product needs, and much easier to reason about, test, and secure than the originally-envisioned microservice mesh.

## 3. Backend module map

```
backend/app/
  api/v1/        one router per domain (auth, tenants, workspaces, companies,
                 contacts, leads, signals, evidence, policies, outreach,
                 templates, do_not_contact, discovery, opportunities,
                 activities, tasks, notes, campaigns, audit)
  core/          config, security (JWT/bcrypt), audit, metrics, rate
                 limiting, logging, network_safety (SSRF), extraction_utils
  db/            SQLAlchemy session/engine, declarative base
  middleware/    request-id correlation + access logging
  models/        one SQLAlchemy model module per domain entity
  schemas/       Pydantic request/response contracts, mirrored 1:1 to models
  services/      business logic: scoring, policy, outreach, outbox,
                 discovery, secure_fetcher, extraction, signal_detection,
                 discovery_worker
  worker.py               outreach outbox worker entrypoint
  discovery_worker.py     discovery pipeline worker entrypoint
  main.py                 FastAPI app assembly
```

Route handlers stay thin: validation and ownership checks, then delegate to `services/`. Nothing in `api/` talks to the database directly beyond ownership lookups.

## 4. Multi-tenancy & security model

- Every domain table carries `tenant_id`; every query is scoped to `current_user.tenant_id`. Cross-tenant access returns 404, not 403 (existence itself is not disclosed).
- RBAC: `owner > admin > manager > analyst > operator > viewer`, enforced per-endpoint via `require_role(...)`, re-checked server-side on every request — the frontend never makes an authorization decision, only a UI-affordance one.
- Auth is JWT Bearer (access + refresh), not cookie-based — CORS defaults to `*` for local dev (safe only because there's no ambient credential to exfiltrate via a wildcard origin) and **must** be an explicit allowlist in production, enforced by `validate_production()` at boot.
- SSRF: the discovery fetcher (`app/services/secure_fetcher.py`) is the only code path allowed to make an outbound HTTP request. Every hop — including redirects — is independently: scheme/port-validated, DNS-resolved once, IP-classified (loopback/link-local/private/multicast/cloud-metadata all blocked), then connected to the exact validated IP literal (never a bare hostname re-resolved by the HTTP client, which is what closes the DNS-rebinding gap).
- The two background workers (`worker.py`, `discovery_worker.py`) use an identical atomic claim/lease/retry/backoff model (`UPDATE ... WHERE status = ... RETURNING`) so concurrent workers never double-process a row, and a crashed worker's claim is automatically recovered after its lease expires. The discovery worker's claim query is intentionally *not* tenant-scoped (one shared process serves every tenant) but every downstream write within a claimed job is threaded through that job's own `tenant_id` — verified by a test that runs two tenants' jobs concurrently and asserts zero cross-references.

## 5. Data flow: Discovery → Outreach in one pass

1. `POST /discovery/jobs` — register a target (deduplicated by canonical URL hash per tenant).
2. `POST /discovery/jobs/{id}/sources` — add candidate URLs.
3. `POST /discovery/sources/{id}/fetch` — secure fetch; success stores a `RawDocument`, any SSRF/validation/network failure marks the source `rejected`/`failed` with a reason and creates nothing downstream.
4. `POST /discovery/sources/{id}/extract` — parses the fetched HTML/text (BeautifulSoup + stdlib parser, no NLP model), get-or-creates a `Company`/`Contact` (deduplicated per tenant by domain/email), writes one `Evidence` row with full provenance in `evidence_metadata` (raw_document_id → discovery_source_id → discovery_job_id).
5. `POST /evidence/{id}/detect-signal` — deterministic classification (a direct `evidence_type` prior, a keyword-confirmed suggestive prior, or a broad keyword scan in a fixed priority order) into the existing `Signal` taxonomy; returns `null` rather than inventing a low-confidence guess when nothing matches.
6. `POST /leads`, `POST /leads/{id}/qualify` (requires cited Evidence — never a bare score), `POST /leads/{id}/score` (deterministic v1: fit/intent/signal/data_confidence/freshness, versioned, with a factor-level breakdown).
7. `POST /policies/evaluate` and `POST /outreach` — the Policy Engine evaluates DNC, consent, qualification, score, evidence freshness, campaign frequency and the global kill switch, in a fixed, versioned order; a `DENY` never reaches a provider. `POST /outreach` requires an explicit `lead_id` (see §7) plus tenant-scoped coherence checks between the named lead, contact and campaign.
8. `POST /outreach/{id}/dispatch` (or the background worker's own poll loop) claims and executes the request through the outbox engine; `DRY_RUN=true` (the default) simulates the send with zero provider calls.

The asynchronous variant of steps 3–5 runs unattended via `python -m app.discovery_worker`, which walks every pending source of a claimed job through the same fetch → extract → detect-signal chain.

## 6. Frontend

Next.js App Router, client-rendered against the FastAPI Bearer-token API (no server-side session, so no RSC-side fetch with credentials — every data-fetching page is a client component). Pages: Dashboard, Discovery (jobs + per-source fetch/extract), Companies, Contacts, Leads (score breakdown, evidence-backed qualification), Evidence, Signals, Campaigns, Outreach, Audit. The frontend never enforces authorization — it hides UI affordances a role can't use, and every action still gets re-checked by the API.

## 7. Known, currently-open items

- `POST /outreach` requires the caller to name the exact `lead_id` (fixed after a production-readiness audit found the endpoint previously guessed "the tenant's newest lead" — see git history / `tests/test_outreach_lead_targeting.py` for the regression suite that pins this down with three leads per tenant and cross-checks that scoring, policy evaluation, and audit all reference the named lead and only that lead).
- The frontend has no UI to create an `OutreachRequest` — the Outreach page can dispatch/cancel existing requests but the send-creation workflow described in §5 step 7 is currently only reachable via the API directly (`/docs` or a script). A production-readiness audit surfaced this; building the missing screen is deliberately not yet scheduled (see project roadmap).

## 8. What's deliberately out of scope for v1

- No ML model for extraction or scoring — both are deterministic, versioned, and fully explainable by design (see `docs/archive/INITIAL_ARCHITECTURE.md` for the abandoned "AI Analysis" stage).
- No queue broker — two polling workers sharing Postgres cover the actual throughput needs.
- WhatsApp/Telegram/Meta providers are not wired: `NoopProvider` backs those channels (`app/services/providers.py`) until each gets its own external account/credentials/sandbox/app review, one channel at a time.
- Email has a real adapter (`SmtpEmailProvider`, generic SMTP — works with any provider: a self-hosted server, Gmail, SES, SendGrid, Mailgun, Postmark...) but it is only *active* when `smtp_host` is configured; local/dev/test and any deployment that leaves it unset keep using `MockEmailProvider`, and `DRY_RUN`/the `outreach_enabled` kill switch still gate every send regardless. `validate_production()` refuses to boot in production with `dry_run=false` and no `smtp_host` set, specifically so a misconfigured deployment can't silently fall back to a fabricated "sent" result.

## 9. Testing & CI

- `backend/tests/` — 380+ pytest tests: unit (services, scoring, policy), integration (real Postgres/Redis via `httpx.ASGITransport`), security (SSRF exhaustive suite, multi-tenant cross-access sweep, RBAC), end-to-end (discovery → outreach dry-run, including a real unmocked SSRF block against a literal metadata IP).
- `frontend/` — `eslint` (flat config) + `next build` (which type-checks) on every change; `npm audit` kept at 0 vulnerabilities.
- `.github/workflows/ci.yml` runs both on every push/PR: Postgres + Redis service containers, `ruff check` + `pytest` for the backend, `npm ci && npm audit && npm run lint && npm run build` for the frontend.
