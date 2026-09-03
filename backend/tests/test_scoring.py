import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.models.evidence import Evidence
from app.models.signal import Signal
from app.services.scoring import (
    SCORING_VERSION,
    compute_score,
    fingerprint_of,
)
from tests.conftest import create_company, create_evidence, register_tenant


def _signal(
    signal_type: str,
    confidence: float = 1.0,
    evidence_id: uuid.UUID | None = None,
    status: str = "new",
    detected_at: datetime | None = None,
):
    return Signal(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        signal_type=signal_type,
        confidence=confidence,
        evidence_id=evidence_id,
        status=status,
        detected_at=detected_at or datetime(2026, 9, 2, tzinfo=UTC),
    )


def _evidence(eid: uuid.UUID, confidence: float = 1.0):
    return Evidence(id=eid, tenant_id=uuid.uuid4(), source_url="https://x/y", confidence=confidence)


async def _score_setup(client, suffix, signal_type="hiring", confidence=1.0):
    headers = await register_tenant(client, f"score-{suffix}", f"score{suffix}@example.com")
    company_id = await create_company(client, headers, suffix)
    ev_id = await create_evidence(client, headers, suffix, company_id)
    await client.post(
        "/api/v1/signals",
        json={
            "company_id": company_id,
            "signal_type": signal_type,
            "confidence": confidence,
            "evidence_id": ev_id,
            "detected_at": "2026-09-02T00:00:00Z",
        },
        headers=headers,
    )
    lead_resp = await client.post(
        "/api/v1/leads", json={"company_id": company_id}, headers=headers
    )
    lead_id = lead_resp.json()["id"]
    return headers, lead_id


# ---------------------------------------------------------------------------
# Pure determinism / explainability unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_score_is_deterministic():
    now = datetime(2026, 9, 3, tzinfo=UTC)
    eid = uuid.uuid4()
    signals = [_signal("hiring", evidence_id=eid)]
    evidence = [_evidence(eid)]
    a = compute_score(signals, evidence, now=now)
    b = compute_score(signals, evidence, now=now)
    assert a.score == b.score
    assert a.to_dict() == b.to_dict()


@pytest.mark.asyncio
async def test_compute_score_explainable_with_evidence_refs():
    now = datetime(2026, 9, 3, tzinfo=UTC)
    eid = uuid.uuid4()
    signals = [_signal("hiring", evidence_id=eid), _signal("funding", evidence_id=eid)]
    evidence = [_evidence(eid)]
    result = compute_score(signals, evidence, now=now)
    d = result.to_dict()
    assert d["scoring_version"] == SCORING_VERSION
    assert 0 <= d["score"] <= 100
    assert set(d["breakdown"].keys()) == {
        "fit",
        "intent",
        "signal",
        "data_confidence",
        "freshness",
    }
    # factor mentions evidence ids for traceability
    all_ev = {e for f in d["factors"] for e in f["evidence_ids"]}
    assert str(eid) in all_ev


@pytest.mark.asyncio
async def test_dismissed_signal_never_contributes():
    now = datetime(2026, 9, 3, tzinfo=UTC)
    active = [_signal("hiring")]
    dismissed = [_signal("hiring", status="dismissed")]
    high = compute_score(active, [_evidence(uuid.uuid4())], now=now)
    low = compute_score(dismissed, [_evidence(uuid.uuid4())], now=now)
    # a dismissed-only set yields the empty-signal floor
    empty = compute_score([], [], now=now)
    assert low.score == empty.score
    assert high.score > low.score


@pytest.mark.asyncio
async def test_low_confidence_reduces_influence():
    now = datetime(2026, 9, 3, tzinfo=UTC)
    hi = compute_score([_signal("funding", confidence=1.0)], [_evidence(uuid.uuid4())], now=now)
    lo = compute_score([_signal("funding", confidence=0.2)], [_evidence(uuid.uuid4())], now=now)
    assert hi.score > lo.score


@pytest.mark.asyncio
async def test_freshness_penalizes_old_data():
    now = datetime(2026, 9, 3, tzinfo=UTC)
    fresh = compute_score(
        [_signal("expansion", detected_at=datetime(2026, 9, 2, tzinfo=UTC))],
        [_evidence(uuid.uuid4())],
        now=now,
    )
    old = compute_score(
        [_signal("expansion", detected_at=datetime(2024, 1, 1, tzinfo=UTC))],
        [_evidence(uuid.uuid4())],
        now=now,
    )
    assert fresh.freshness > old.freshness
    assert fresh.score > old.score


@pytest.mark.asyncio
async def test_fingerprint_is_stable():
    a = fingerprint_of({"type": "x", "value": 1})
    assert a == fingerprint_of({"value": 1, "type": "x"})
    assert isinstance(a, str) and len(a) == 64


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_score_api_deterministic(client: AsyncClient):
    headers, lead_id = await _score_setup(client, "det")
    url = f"/api/v1/leads/{lead_id}/score"
    first = await client.post(url, headers=headers)
    second = await client.post(url, headers=headers)
    assert first.status_code == 200, first.text
    assert second.status_code == 200
    assert first.json()["score"] == second.json()["score"]
    assert first.json()["scoring_version"] == SCORING_VERSION


@pytest.mark.asyncio
async def test_score_persists_on_lead(client: AsyncClient):
    headers, lead_id = await _score_setup(client, "persist")
    url = f"/api/v1/leads/{lead_id}/score"
    resp = await client.post(url, headers=headers)
    assert resp.status_code == 200, resp.text
    score = resp.json()["score"]

    lead = await client.get(f"/api/v1/leads/{lead_id}", headers=headers)
    body = lead.json()
    assert body["score"] == score
    assert body["scoring_version"] == SCORING_VERSION
    assert "factors" in body["score_explanation"]


@pytest.mark.asyncio
async def test_score_is_traceable_to_source(client: AsyncClient):
    headers, lead_id = await _score_setup(client, "trace")
    ev_list = await client.get("/api/v1/evidence", headers=headers)
    evidence = ev_list.json()[0]
    evidence_id = evidence["id"]

    resp = await client.post(f"/api/v1/leads/{lead_id}/score", headers=headers)
    factors = resp.json()["factors"]
    factor_ev_ids = {e for f in factors for e in f["evidence_ids"]}
    assert evidence_id in factor_ev_ids


@pytest.mark.asyncio
async def test_score_cross_tenant_isolation(client: AsyncClient):
    # tenant A with one signal
    owner_a = await register_tenant(client, "score-iso-a", "scoreisa@example.com")
    company_a = await create_company(client, owner_a, "IsoA")
    ev_a = await create_evidence(client, owner_a, "IsoA", company_a)
    await client.post(
        "/api/v1/signals",
        json={
            "company_id": company_a,
            "signal_type": "hiring",
            "evidence_id": ev_a,
            "detected_at": "2026-09-02T00:00:00Z",
        },
        headers=owner_a,
    )
    lead_a_resp = await client.post(
        "/api/v1/leads", json={"company_id": company_a}, headers=owner_a
    )
    lead_a = lead_a_resp.json()["id"]

    # tenant B with multiple signals
    owner_b = await register_tenant(client, "score-iso-b", "scoreisb@example.com")
    company_b = await create_company(client, owner_b, "IsoB")
    for st in ["hiring", "funding", "expansion", "acquisition"]:
        ev_b = await create_evidence(client, owner_b, f"B-{st}", company_b)
        await client.post(
            "/api/v1/signals",
            json={
                "company_id": company_b,
                "signal_type": st,
                "evidence_id": ev_b,
                "detected_at": "2026-09-02T00:00:00Z",
            },
            headers=owner_b,
        )

    score_b = await client.post("/api/v1/leads", json={"company_id": company_b}, headers=owner_b)
    lead_b = score_b.json()["id"]

    sa = await client.post(f"/api/v1/leads/{lead_a}/score", headers=owner_a)
    sb = await client.post(f"/api/v1/leads/{lead_b}/score", headers=owner_b)
    # B's richer signal set must not leak into A's score
    assert sa.json()["score"] < sb.json()["score"]