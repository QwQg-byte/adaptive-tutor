"""Integration checks against an explicitly isolated Neo4j database."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest

from database.neo4j_exceptions import Neo4jConnectionError
from database.neo4j_service import Neo4jService


pytestmark = pytest.mark.integration


async def connect_with_retry(service: Neo4jService) -> None:
    last_error = None
    for _ in range(60):
        try:
            await service.connect()
            return
        except Neo4jConnectionError as exc:
            last_error = exc
            await asyncio.sleep(1)
    raise AssertionError("isolated Neo4j did not become ready") from last_error


@pytest.mark.asyncio
async def test_isolated_database_read_write_statistics_and_path():
    if os.getenv("TEST_NEO4J_ISOLATED") != "1":
        pytest.skip("set TEST_NEO4J_ISOLATED=1 only for a disposable test database")

    required = ["TEST_NEO4J_URI", "TEST_NEO4J_USER", "TEST_NEO4J_PASSWORD"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        pytest.fail(f"missing isolated Neo4j settings: {', '.join(missing)}")

    run_id = f"phase6-{uuid4()}"
    base_id = f"IT_BASE_{uuid4().hex}"
    target_id = f"IT_TARGET_{uuid4().hex}"
    service = Neo4jService()
    service.uri = os.environ["TEST_NEO4J_URI"]
    service.user = os.environ["TEST_NEO4J_USER"]
    service.password = os.environ["TEST_NEO4J_PASSWORD"]
    service.database = os.getenv("TEST_NEO4J_DATABASE", "neo4j")

    await connect_with_retry(service)
    try:
        created = await service.execute_write(
            """
            CREATE (base:KnowledgeNode {
                id: $base_id, name: 'Integration Base', integration_test_run: $run_id
            })
            CREATE (target:KnowledgeNode {
                id: $target_id, name: 'Integration Target', integration_test_run: $run_id
            })
            CREATE (target)-[:PREREQUISITE]->(base)
            RETURN target.id AS target_id, base.id AS base_id
            """,
            {"base_id": base_id, "target_id": target_id, "run_id": run_id},
        )
        assert created == [{"target_id": target_id, "base_id": base_id}]

        rows = await service.execute_read(
            "MATCH (n {integration_test_run: $run_id}) RETURN count(n) AS count",
            {"run_id": run_id},
        )
        assert rows[0]["count"] == 2

        path = await service.find_shortest_path(target_id, base_id, max_depth=2)
        assert path is not None
        assert [node["id"] for node in path["nodes"]] == [target_id, base_id]

        statistics = await service.get_statistics(force_refresh=True)
        assert statistics["nodes"]["KnowledgeNode"] >= 2
        assert statistics["relationships"]["PREREQUISITE"] >= 1
    finally:
        await service.execute_write(
            "MATCH (n {integration_test_run: $run_id}) DETACH DELETE n",
            {"run_id": run_id},
        )
        await service.close()
