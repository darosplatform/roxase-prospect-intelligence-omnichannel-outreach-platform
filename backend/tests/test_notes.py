import pytest


@pytest.mark.asyncio
async def test_create_note(company_auth):
    client, headers, company_id = company_auth
    payload = {
        "company_id": company_id,
        "content": "Important context about the company",
    }
    response = await client.post("/api/v1/notes", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["content"] == "Important context about the company"
    assert data["author_user_id"] is not None
    assert data["tenant_id"] is not None


@pytest.mark.asyncio
async def test_list_notes(company_auth):
    client, headers, _ = company_auth
    await client.post(
        "/api/v1/notes",
        json={"content": "A note"},
        headers=headers,
    )
    response = await client.get("/api/v1/notes", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["content"] == "A note"