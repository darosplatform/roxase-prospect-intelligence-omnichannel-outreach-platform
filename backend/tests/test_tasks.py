import pytest


@pytest.mark.asyncio
async def test_create_task(company_auth):
    client, headers, company_id = company_auth
    payload = {
        "company_id": company_id,
        "title": "Follow up with CEO",
        "status": "todo",
        "priority": "high",
    }
    response = await client.post("/api/v1/tasks", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Follow up with CEO"
    assert data["status"] == "todo"
    assert data["priority"] == "high"


@pytest.mark.asyncio
async def test_update_task(company_auth):
    client, headers, _ = company_auth
    create_resp = await client.post(
        "/api/v1/tasks",
        json={"title": "Task", "status": "todo"},
        headers=headers,
    )
    task_id = create_resp.json()["id"]

    patch = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "done", "priority": "urgent"},
        headers=headers,
    )
    assert patch.status_code == 200
    data = patch.json()
    assert data["status"] == "done"
    assert data["priority"] == "urgent"
    assert data["completed_at"] is not None


@pytest.mark.asyncio
async def test_list_tasks(company_auth):
    client, headers, _ = company_auth
    await client.post("/api/v1/tasks", json={"title": "Task 1"}, headers=headers)
    response = await client.get("/api/v1/tasks", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1