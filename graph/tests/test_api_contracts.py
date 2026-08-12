"""HTTP-level FastAPI contracts for validation, errors, and phase 5 planning."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from database.neo4j_exceptions import Neo4jConnectionError
from main import app
from observability import runtime_metrics


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


@pytest.mark.asyncio
async def test_plan_endpoint_returns_ordered_steps_and_preference(client):
    with (
        patch(
            "api.path._resolve_knowledge_node",
            new=AsyncMock(return_value={"id": "TARGET", "name": "目标"}),
        ),
        patch(
            "api.path._fetch_prerequisite_subgraph",
            new=AsyncMock(return_value=(
                {"BASE": {"id": "BASE", "name": "基础", "depth": 1}},
                [("TARGET", "BASE")],
            )),
        ),
        patch(
            "api.path._fetch_questions_for_nodes",
            new=AsyncMock(return_value={"BASE": [{"id": "Q1"}]}),
        ),
    ):
        response = await client.post(
            "/api/v1/path/plan",
            json={
                "target": "目标",
                "max_depth": 4,
                "difficulty_preference": "challenge",
                "questions_per_step": 2,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["difficulty_preference"] == "challenge"
    assert [step["id"] for step in payload["data"]["steps"]] == ["BASE", "TARGET"]
    assert payload["data"]["steps"][0]["questions"][0]["id"] == "Q1"


@pytest.mark.asyncio
async def test_path_request_boundary_is_rejected_before_database_access(client):
    response = await client.post(
        "/api/v1/path/shortest",
        json={"start": "A", "end": "B", "max_depth": 11},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_database_connection_error_maps_to_503_without_internal_details(client):
    with patch(
        "api.graph.neo4j_service.get_statistics",
        new=AsyncMock(side_effect=Neo4jConnectionError("secret internal detail")),
    ):
        response = await client.get("/api/v1/graph/statistics")

    assert response.status_code == 503
    assert response.json()["message"] == "数据库暂时不可用"
    assert "secret internal detail" not in response.text


@pytest.mark.asyncio
async def test_runtime_metrics_use_route_templates_and_timing_header(client):
    runtime_metrics.reset()

    health = await client.get("/health")
    metrics = await client.get("/metrics")

    assert health.status_code == 200
    assert float(health.headers["X-Process-Time-Ms"]) >= 0
    snapshot = metrics.json()
    assert snapshot["requests"]["count"] >= 1
    assert "/health" in snapshot["requests"]["routes"]
    assert "neo4j_queries" in snapshot
