import pytest
from httpx import AsyncClient

from tests.conftest import create_company, create_contact, register_tenant


@pytest.mark.asyncio
async def test_search_companies_by_name_domain_industry(client: AsyncClient):
    headers = await register_tenant(client, "srch-co", "srchco@example.com")
    acme = await client.post(
        "/api/v1/companies",
        json={
            "legal_name": "Acme Corp",
            "domain": "acme.io",
            "industry": "Aerospace",
        },
        headers=headers,
    )
    beta = await client.post(
        "/api/v1/companies",
        json={"legal_name": "Beta Labs", "domain": "beta.dev", "industry": "Bio"},
        headers=headers,
    )
    acme_id = acme.json()["id"]
    beta_id = beta.json()["id"]

    by_name = await client.get("/api/v1/companies?q=acme", headers=headers)
    ids = [c["id"] for c in by_name.json()]
    assert acme_id in ids and beta_id not in ids

    by_domain = await client.get("/api/v1/companies?q=beta.dev", headers=headers)
    ids = [c["id"] for c in by_domain.json()]
    assert beta_id in ids and acme_id not in ids

    by_industry = await client.get("/api/v1/companies?q=aerospace", headers=headers)
    ids = [c["id"] for c in by_industry.json()]
    assert acme_id in ids and beta_id not in ids


@pytest.mark.asyncio
async def test_search_companies_empty_q_returns_all(client: AsyncClient):
    headers = await register_tenant(client, "srch-co2", "srchco2@example.com")
    await create_company(client, headers, "One")
    await create_company(client, headers, "Two")
    all_resp = await client.get("/api/v1/companies?q=", headers=headers)
    assert all_resp.status_code == 200
    assert len(all_resp.json()) == 2


@pytest.mark.asyncio
async def test_search_contacts_by_name_email_title(client: AsyncClient):
    headers = await register_tenant(client, "srch-ct", "srchct@example.com")
    c1 = await client.post(
        "/api/v1/contacts",
        json={
            "first_name": "Jane",
            "last_name": "Smith",
            "email": "jane@x.com",
            "job_title": "CTO",
        },
        headers=headers,
    )
    c2 = await client.post(
        "/api/v1/contacts",
        json={"first_name": "Bob", "last_name": "Jones", "email": "bob@x.com"},
        headers=headers,
    )
    c1_id = c1.json()["id"]
    c2_id = c2.json()["id"]

    by_name = await client.get("/api/v1/contacts?q=smith", headers=headers)
    assert c1_id in [c["id"] for c in by_name.json()]
    assert c2_id not in [c["id"] for c in by_name.json()]

    by_email = await client.get("/api/v1/contacts?q=bob@x.com", headers=headers)
    assert c2_id in [c["id"] for c in by_email.json()]
    assert c1_id not in [c["id"] for c in by_email.json()]

    by_title = await client.get("/api/v1/contacts?q=cto", headers=headers)
    assert c1_id in [c["id"] for c in by_title.json()]


@pytest.mark.asyncio
async def test_contact_get_by_id(client: AsyncClient):
    headers = await register_tenant(client, "srch-ct2", "srchct2@example.com")
    contact_id = await create_contact(client, headers, "ById")
    ok = await client.get(f"/api/v1/contacts/{contact_id}", headers=headers)
    assert ok.status_code == 200
    assert ok.json()["id"] == contact_id

    missing = await client.get(
        f"/api/v1/contacts/{'00000000-0000-0000-0000-000000000000'}",
        headers=headers,
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_search_signals_by_title_description(client: AsyncClient):
    headers = await register_tenant(client, "srch-sig", "srchsig@example.com")
    company_id = await create_company(client, headers, "Sig")
    s1 = await client.post(
        "/api/v1/signals",
        json={
            "company_id": company_id,
            "signal_type": "funding",
            "title": "Round A closed",
            "description": "raised 10M",
            "source_name": "TechCrunch",
        },
        headers=headers,
    )
    s2 = await client.post(
        "/api/v1/signals",
        json={
            "company_id": company_id,
            "signal_type": "hiring",
            "title": "New VP",
            "description": "hiring in SF",
            "source_name": "LinkedIn",
        },
        headers=headers,
    )
    s1_id = s1.json()["id"]
    s2_id = s2.json()["id"]

    by_title = await client.get("/api/v1/signals?q=round+a", headers=headers)
    assert s1_id in [s["id"] for s in by_title.json()]
    assert s2_id not in [s["id"] for s in by_title.json()]
    assert by_title.json()[0]["title"] == "Round A closed"

    by_desc = await client.get("/api/v1/signals?q=hiring", headers=headers)
    assert s2_id in [s["id"] for s in by_desc.json()]

    by_source = await client.get("/api/v1/signals?q=techcrunch", headers=headers)
    assert s1_id in [s["id"] for s in by_source.json()]


@pytest.mark.asyncio
async def test_search_opportunities_by_name_description(client: AsyncClient):
    headers = await register_tenant(client, "srch-opp", "srchopp@example.com")
    company_id = await create_company(client, headers, "Opp")
    o1 = await client.post(
        "/api/v1/opportunities",
        json={
            "company_id": company_id,
            "name": "Expansion Deal",
            "description": "enterprise contract",
        },
        headers=headers,
    )
    o2 = await client.post(
        "/api/v1/opportunities",
        json={"company_id": company_id, "name": "SMB Upsell"},
        headers=headers,
    )
    o1_id = o1.json()["id"]
    o2_id = o2.json()["id"]

    by_name = await client.get("/api/v1/opportunities?q=expansion", headers=headers)
    assert o1_id in [o["id"] for o in by_name.json()]
    assert o2_id not in [o["id"] for o in by_name.json()]

    by_desc = await client.get("/api/v1/opportunities?q=enterprise", headers=headers)
    assert o1_id in [o["id"] for o in by_desc.json()]
    assert o2_id not in [o["id"] for o in by_desc.json()]


@pytest.mark.asyncio
async def test_search_is_cross_tenant_isolated(client: AsyncClient):
    h_a = await register_tenant(client, "srch-isa", "srchisa@example.com")
    h_b = await register_tenant(client, "srch-isb", "srchisb@example.com")
    c = await client.post(
        "/api/v1/companies",
        json={"legal_name": "SecretCo", "domain": "secret.co"},
        headers=h_a,
    )
    secret_id = c.json()["id"]

    in_b = await client.get("/api/v1/companies?q=secret", headers=h_b)
    assert secret_id not in [x["id"] for x in in_b.json()]