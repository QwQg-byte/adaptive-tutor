"""Run read-only FastAPI integration checks against the configured Neo4j."""

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from time import perf_counter

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "application" / "backend"
sys.path.insert(0, str(BACKEND_DIR))
# Verification may run beside the acceptance server; avoid competing file sinks.
os.environ["LOG_FILE"] = ""

from main import app  # noqa: E402
from database.neo4j_exceptions import (  # noqa: E402
    Neo4jConnectionError,
    Neo4jQueryError,
    Neo4jQueryTimeoutError,
)
from database.neo4j_service import neo4j_service  # noqa: E402


LEGACY_ELEMENT_ID = re.compile(r"^\d+:[^:]+:\d+$")


async def require_success(client: httpx.AsyncClient, method: str, url: str, **kwargs):
    response = await client.request(method, url, **kwargs)
    assert response.status_code == 200, (url, response.status_code, response.text)
    payload = response.json()
    assert payload.get("success") is True, (url, payload)
    return payload["data"]


def assert_business_ids(ids):
    values = list(ids)
    assert values, "expected at least one business ID"
    assert all(value and not LEGACY_ELEMENT_ID.match(value) for value in values), values


async def main() -> None:
    timings = {}
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://stage2.local",
            timeout=30,
        ) as client:
            health = await client.get("/health")
            assert health.status_code == 200
            assert health.json()["neo4j_connected"] is True

            checks = [
                ("graph", "GET", "/api/v1/graph/data?limit=30", {}),
                ("knowledge_list", "GET", "/api/v1/graph/knowledge-points?limit=10", {}),
                ("knowledge_detail", "GET", "/api/v1/graph/knowledge-point/NODE_002", {}),
                ("question_detail", "GET", "/api/v1/graph/question/MT1001", {}),
                ("search", "GET", "/api/v1/search/keyword?keyword=数据&limit=10", {}),
                (
                    "shortest_path",
                    "POST",
                    "/api/v1/path/shortest",
                    {"json": {"start": "NODE_002", "end": "NODE_001", "max_depth": 3}},
                ),
                (
                    "learning_plan",
                    "POST",
                    "/api/v1/path/plan",
                    {
                        "json": {
                            "target": "NODE_002",
                            "max_depth": 3,
                            "mastered": [],
                            "questions_per_step": 1,
                        }
                    },
                ),
                ("home", "GET", "/api/v1/graph/home/data", {}),
            ]
            results = {}
            for name, method, url, kwargs in checks:
                started = perf_counter()
                results[name] = await require_success(client, method, url, **kwargs)
                timings[name] = round((perf_counter() - started) * 1000, 1)

            assert_business_ids(node["id"] for node in results["graph"]["nodes"])
            assert_business_ids(node["id"] for node in results["knowledge_list"])
            assert results["knowledge_detail"]["knowledge_point"]["id"] == "NODE_002"
            assert results["question_detail"]["question"]["id"] == "MT1001"
            assert_business_ids(node["id"] for node in results["shortest_path"]["nodes"])
            assert results["learning_plan"]["target"]["id"] == "NODE_002"

            missing = await client.get("/api/v1/graph/node/DOES_NOT_EXIST")
            assert missing.status_code == 404, missing.text

            started = perf_counter()
            concurrent = await asyncio.gather(
                *[
                    client.get("/api/v1/graph/node/NODE_002")
                    for _ in range(20)
                ]
            )
            timings["20_concurrent_node_requests"] = round(
                (perf_counter() - started) * 1000,
                1,
            )
            assert all(response.status_code == 200 for response in concurrent)

            original_get_statistics = neo4j_service.get_statistics
            database_errors = [
                (Neo4jConnectionError("private connection detail"), 503),
                (Neo4jQueryTimeoutError("private timeout detail"), 504),
                (Neo4jQueryError("private query detail"), 500),
            ]
            try:
                for error, expected_status in database_errors:
                    async def fail_statistics(current_error=error):
                        raise current_error

                    neo4j_service.get_statistics = fail_statistics
                    response = await client.get("/api/v1/graph/statistics")
                    assert response.status_code == expected_status, response.text
                    assert "private" not in response.text
            finally:
                neo4j_service.get_statistics = original_get_statistics
            timings["database_error_mapping"] = "503/504/500"

    print(
        json.dumps(
            {
                "status": "ok",
                "checks": list(timings),
                "timings_ms": timings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
