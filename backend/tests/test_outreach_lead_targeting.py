"""Regression suite for the lead_id targeting bug: POST /outreach used to
silently attach every request to "whichever lead is newest in the tenant"
instead of the lead the caller actually meant. With a single lead per
tenant (every other test file's setup) that bug is invisible — it only
shows up with multiple leads, which is exactly what this file sets up.

    Tenant A
     |-- Lead A1 (Company A1, funding evidence, high score)
     |-- Lead A2 (Company A2, hiring evidence, different score)
     `-- Lead A3 (Company A3, unrelated)

    POST outreach lead_id=A1 -> policy/score/audit/OutreachRequest/worker
    dispatch must all reference A1, never A2 or A3.
    POST outreach lead_id=A2 -> same proof, and nothing from A1 leaks in.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import register_tenant


async def _build_lead(client: AsyncClient, headers: dict, suffix: str, evidence_type: str):
    company = (
        await client.post(
            "/api/v1/companies",
            json={"legal_name": f"Targeting {suffix}", "domain": f"target{suffix}.example"},
            headers=headers,
        )
    ).json()
    contact = (
        await client.post(
            "/api/v1/contacts",
            json={
                "company_id": company["id"],
                "first_name": suffix,
                "email": f"{suffix}@target{suffix}.example",
            },
            headers=headers,
        )
    ).json()
    evidence = (
        await client.post(
            "/api/v1/evidence",
            json={
                "company_id": company["id"],
                "source_url": f"https://target{suffix}.example/news",
                "evidence_type": evidence_type,
                "title": f"{suffix} news",
                "confidence": 1.0,
            },
            headers=headers,
        )
    ).json()
    # Policy's evidence_ids are signal-derived (see _gather_context), not
    # the qualification evidence directly — detect a signal so the
    # per-lead evidence_ids assertions below are actually exercising
    # something, not just an empty list.
    signal_resp = await client.post(
        f"/api/v1/evidence/{evidence['id']}/detect-signal", headers=headers
    )
    assert signal_resp.status_code == 200 and signal_resp.json() is not None, signal_resp.text
    lead = (
        await client.post(
            "/api/v1/leads",
            json={"company_id": company["id"], "contact_id": contact["id"], "status": "new"},
            headers=headers,
        )
    ).json()
    qualify = await client.post(
        f"/api/v1/leads/{lead['id']}/qualify",
        json={"status": "qualified", "evidence_ids": [evidence["id"]]},
        headers=headers,
    )
    assert qualify.status_code == 200, qualify.text
    score = await client.post(f"/api/v1/leads/{lead['id']}/score", headers=headers)
    assert score.status_code == 200, score.text
    return {
        "company_id": company["id"],
        "contact_id": contact["id"],
        "evidence_id": evidence["id"],
        "lead_id": lead["id"],
        "score": score.json()["score"],
    }


@pytest.fixture
async def three_leads(client: AsyncClient):
    headers = await register_tenant(client, "target-a", "target-a@example.com")
    a1 = await _build_lead(client, headers, "a1", "funding")
    a2 = await _build_lead(client, headers, "a2", "hiring")
    a3 = await _build_lead(client, headers, "a3", "partnership")

    campaign = (
        await client.post(
            "/api/v1/campaigns",
            json={
                "name": "Targeting campaign",
                "status": "running",
                "channel": "email",
                "policy": {
                    "dry_run": True,
                    "allowed_channels": ["email"],
                    "min_lead_score": 1,
                    "require_qualification": True,
                    "require_evidence": True,
                },
            },
            headers=headers,
        )
    ).json()
    template = (
        await client.post(
            "/api/v1/templates",
            json={"name": "Targeting tmpl", "channel": "email", "body": "Hi"},
            headers=headers,
        )
    ).json()
    for lead in (a1, a2, a3):
        await client.post(
            "/api/v1/consents",
            json={"contact_id": lead["contact_id"], "basis": "consent", "channel": "email"},
            headers=headers,
        )

    return {
        "headers": headers,
        "campaign_id": campaign["id"],
        "template_id": template["id"],
        "a1": a1,
        "a2": a2,
        "a3": a3,
    }


@pytest.mark.asyncio
async def test_outreach_targets_exactly_the_named_lead(client: AsyncClient, three_leads):
    ctx = three_leads
    a1, a2 = ctx["a1"], ctx["a2"]

    # -- Request 1: explicitly for A1 --------------------------------------
    ev1 = await client.post(
        "/api/v1/policies/evaluate",
        json={
            "lead_id": a1["lead_id"],
            "campaign_id": ctx["campaign_id"],
            "contact_id": a1["contact_id"],
            "channel": "email",
        },
        headers=ctx["headers"],
    )
    assert ev1.status_code == 200, ev1.text
    assert a1["evidence_id"] in ev1.json()["evidence_ids"]
    assert a2["evidence_id"] not in ev1.json()["evidence_ids"]

    or1 = await client.post(
        "/api/v1/outreach",
        json={
            "lead_id": a1["lead_id"],
            "contact_id": a1["contact_id"],
            "campaign_id": ctx["campaign_id"],
            "channel": "email",
            "template_id": ctx["template_id"],
        },
        headers=ctx["headers"],
    )
    assert or1.status_code == 201, or1.text
    req1 = or1.json()
    assert req1["lead_id"] == a1["lead_id"]
    assert req1["lead_id"] != a2["lead_id"]

    dispatch1 = await client.post(
        f"/api/v1/outreach/{req1['id']}/dispatch", headers=ctx["headers"]
    )
    assert dispatch1.status_code == 200, dispatch1.text
    assert dispatch1.json()["lead_id"] == a1["lead_id"]

    # -- Request 2: explicitly for A2 — must not see anything from A1 -----
    ev2 = await client.post(
        "/api/v1/policies/evaluate",
        json={
            "lead_id": a2["lead_id"],
            "campaign_id": ctx["campaign_id"],
            "contact_id": a2["contact_id"],
            "channel": "email",
        },
        headers=ctx["headers"],
    )
    assert ev2.status_code == 200, ev2.text
    assert a2["evidence_id"] in ev2.json()["evidence_ids"]
    assert a1["evidence_id"] not in ev2.json()["evidence_ids"]

    or2 = await client.post(
        "/api/v1/outreach",
        json={
            "lead_id": a2["lead_id"],
            "contact_id": a2["contact_id"],
            "campaign_id": ctx["campaign_id"],
            "channel": "email",
            "template_id": ctx["template_id"],
        },
        headers=ctx["headers"],
    )
    assert or2.status_code == 201, or2.text
    req2 = or2.json()
    assert req2["lead_id"] == a2["lead_id"]
    assert req2["id"] != req1["id"]
    assert req2["idempotency_key"] != req1["idempotency_key"]

    dispatch2 = await client.post(
        f"/api/v1/outreach/{req2['id']}/dispatch", headers=ctx["headers"]
    )
    assert dispatch2.status_code == 200, dispatch2.text
    assert dispatch2.json()["lead_id"] == a2["lead_id"]

    # -- Audit: each request's own audit trail is scoped to itself, never
    # bleeding into the other request's entity_id --------------------------
    audit_req1 = await client.get(
        "/api/v1/audit", params={"entity_id": req1["id"]}, headers=ctx["headers"]
    )
    audit_req2 = await client.get(
        "/api/v1/audit", params={"entity_id": req2["id"]}, headers=ctx["headers"]
    )
    assert audit_req1.status_code == 200 and audit_req2.status_code == 200
    assert len(audit_req1.json()) >= 1
    assert len(audit_req2.json()) >= 1
    assert all(e["entity_id"] == req1["id"] for e in audit_req1.json())
    assert all(e["entity_id"] == req2["id"] for e in audit_req2.json())

    # -- OutreachRequest rows themselves are the definitive record --------
    listed = await client.get("/api/v1/outreach", headers=ctx["headers"])
    by_id = {o["id"]: o for o in listed.json()}
    assert by_id[req1["id"]]["lead_id"] == a1["lead_id"]
    assert by_id[req2["id"]]["lead_id"] == a2["lead_id"]
    assert by_id[req1["id"]]["lead_id"] != by_id[req2["id"]]["lead_id"]


@pytest.mark.asyncio
async def test_outreach_rejects_contact_from_a_different_company_than_the_lead(
    client: AsyncClient, three_leads
):
    """The historical bug picked an unrelated lead silently; the fix must
    reject an unrelated pairing explicitly rather than silently misfile it
    under the wrong lead."""
    ctx = three_leads
    a1, a2 = ctx["a1"], ctx["a2"]

    resp = await client.post(
        "/api/v1/outreach",
        json={
            "lead_id": a1["lead_id"],
            "contact_id": a2["contact_id"],  # belongs to a DIFFERENT company/lead
            "campaign_id": ctx["campaign_id"],
            "channel": "email",
            "template_id": ctx["template_id"],
        },
        headers=ctx["headers"],
    )
    assert resp.status_code == 422
    assert "company" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_outreach_requires_lead_id(client: AsyncClient, three_leads):
    ctx = three_leads
    resp = await client.post(
        "/api/v1/outreach",
        json={
            "contact_id": ctx["a1"]["contact_id"],
            "campaign_id": ctx["campaign_id"],
            "channel": "email",
            "template_id": ctx["template_id"],
        },
        headers=ctx["headers"],
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_outreach_rejects_lead_from_another_tenant(client: AsyncClient, three_leads):
    ctx = three_leads
    other_headers = await register_tenant(client, "target-b", "target-b@example.com")
    resp = await client.post(
        "/api/v1/outreach",
        json={
            "lead_id": ctx["a1"]["lead_id"],
            "channel": "email",
        },
        headers=other_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_outreach_audit_denied_event_references_the_correct_lead(
    client: AsyncClient, three_leads
):
    ctx = three_leads
    a2 = ctx["a2"]
    await client.post(
        "/api/v1/do-not-contact",
        json={"contact_id": a2["contact_id"], "channel": "email", "reason": "opt out"},
        headers=ctx["headers"],
    )
    resp = await client.post(
        "/api/v1/outreach",
        json={
            "lead_id": a2["lead_id"],
            "contact_id": a2["contact_id"],
            "campaign_id": ctx["campaign_id"],
            "channel": "email",
            "template_id": ctx["template_id"],
        },
        headers=ctx["headers"],
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "denied"
    assert resp.json()["lead_id"] == a2["lead_id"]
