"""Read-only Schema, query-plan and API benchmark verification for phase 3."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from neo4j import GraphDatabase


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "application" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
# Verification may run beside the acceptance server; avoid competing file sinks.
os.environ["LOG_FILE"] = ""

from config import settings  # noqa: E402
from database.neo4j_service import neo4j_service  # noqa: E402
from main import app  # noqa: E402


EXPECTED_CONSTRAINTS = {
    "knowledge_node_id_unique",
    "knowledge_node_node_id_unique",
    "question_id_unique",
}
EXPECTED_INDEXES = {
    *EXPECTED_CONSTRAINTS,
    "knowledge_node_name_idx",
    "knowledge_node_chapter_id_idx",
    "question_difficulty_idx",
    "question_category1_idx",
    "question_category1_id_idx",
    "question_difficulty_id_idx",
    "content_search_fulltext",
}
ENDPOINTS = (
    ("graph_data_300", "/api/v1/graph/data?limit=300", 3, 2),
    ("statistics", "/api/v1/graph/statistics", 0, 0),
    ("home", "/api/v1/graph/home/data", 1, 1),
    ("knowledge_detail", "/api/v1/graph/knowledge-point/NODE_001", 1, 1),
    ("questions_page", "/api/v1/graph/questions?page=1&page_size=20", 2, 2),
    (
        "search_keyword",
        "/api/v1/search/keyword?keyword=%E6%8E%92%E5%BA%8F&limit=20",
        1,
        1,
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _plan_value(plan: Any, attribute: str, dict_key: str, default: Any) -> Any:
    if isinstance(plan, dict):
        return plan.get(dict_key, default)
    return getattr(plan, attribute, default)


def flatten_profile(plan: Any) -> list[dict[str, Any]]:
    if plan is None:
        return []
    row = {
        "operator": _plan_value(plan, "operator_type", "operatorType", "unknown"),
        "rows": _plan_value(plan, "records", "rows", 0),
        "db_hits": _plan_value(plan, "db_hits", "dbHits", 0),
    }
    children = _plan_value(plan, "children", "children", [])
    return [row, *(item for child in children for item in flatten_profile(child))]


def profile_query(session, name: str, query: str, parameters: dict[str, Any]) -> dict[str, Any]:
    result = session.run(f"PROFILE {query}", parameters)
    summary = result.consume()
    operators = flatten_profile(summary.profile)
    return {
        "name": name,
        "operators": [row["operator"] for row in operators],
        "rows": sum(int(row["rows"] or 0) for row in operators),
        "db_hits": sum(int(row["db_hits"] or 0) for row in operators),
    }


def inspect_database() -> dict[str, Any]:
    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD.get_secret_value()),
    )
    try:
        with driver.session(database=settings.NEO4J_DATABASE) as session:
            component = session.run(
                "CALL dbms.components() YIELD versions, edition "
                "RETURN versions[0] AS version, edition"
            ).single().data()
            constraints = [
                row.data()
                for row in session.run(
                    "SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties "
                    "RETURN * ORDER BY name"
                )
            ]
            indexes = [
                row.data()
                for row in session.run(
                    "SHOW INDEXES YIELD name, type, state, populationPercent, "
                    "labelsOrTypes, properties RETURN * ORDER BY name"
                )
            ]
            samples = session.run(
                "MATCH (n:KnowledgeNode {id: 'NODE_001'}) "
                "MATCH (q:Question) "
                "WHERE q.category1 IS NOT NULL "
                "RETURN n.name AS knowledge_name, q.category1 AS category, "
                "q.id AS question_id LIMIT 1"
            ).single().data()
            plans = [
                profile_query(
                    session,
                    "knowledge_id_lookup",
                    "MATCH (n:KnowledgeNode) WHERE n.id = $id RETURN n.name",
                    {"id": "NODE_001"},
                ),
                profile_query(
                    session,
                    "knowledge_name_lookup",
                    "MATCH (n:KnowledgeNode) WHERE n.name = $name RETURN n.id",
                    {"name": samples["knowledge_name"]},
                ),
                profile_query(
                    session,
                    "question_cursor_page",
                    "MATCH (q:Question) "
                    "WHERE q.category1 = $category AND q.id > $after_id "
                    "RETURN q.id ORDER BY q.id LIMIT 20",
                    {
                        "category": samples["category"],
                        "after_id": samples["question_id"],
                    },
                ),
            ]
            fulltext_count = session.run(
                "CALL db.index.fulltext.queryNodes($index_name, $query) "
                "YIELD node, score RETURN count(node) AS count, max(score) AS max_score",
                {
                    "index_name": settings.NEO4J_FULLTEXT_INDEX_NAME,
                    "query": "排序",
                },
            ).single().data()
    finally:
        driver.close()

    constraint_names = {row["name"] for row in constraints}
    index_names = {row["name"] for row in indexes}
    online_indexes = {
        row["name"] for row in indexes if row.get("state") == "ONLINE"
    }
    return {
        "component": component,
        "schema": {
            "constraints": constraints,
            "indexes": indexes,
            "missing_constraints": sorted(EXPECTED_CONSTRAINTS - constraint_names),
            "missing_indexes": sorted(EXPECTED_INDEXES - index_names),
            "offline_indexes": sorted(EXPECTED_INDEXES - online_indexes),
        },
        "fulltext": fulltext_count,
        "profiles": plans,
    }


async def benchmark_endpoints(samples: int) -> dict[str, Any]:
    if not 1 <= samples <= 20:
        raise ValueError("samples 必须在 1 到 20 之间")

    startup_started = time.perf_counter()
    await neo4j_service.connect()
    await neo4j_service.get_statistics(force_refresh=True)
    startup_ms = (time.perf_counter() - startup_started) * 1000
    original_execute = neo4j_service._execute
    current = {"query_count": 0, "db_ms": 0.0}

    async def counted_execute(*args, **kwargs):
        started = time.perf_counter()
        current["query_count"] += 1
        try:
            return await original_execute(*args, **kwargs)
        finally:
            current["db_ms"] += (time.perf_counter() - started) * 1000

    neo4j_service._execute = counted_execute
    output = {
        "startup_prewarm": {
            "median_total_ms": round(startup_ms, 3),
            "passed": True,
        }
    }
    try:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            for name, path, cold_limit, warm_limit in ENDPOINTS:
                current.update(query_count=0, db_ms=0.0)
                cold_response = await client.get(path)
                cold_query_count = current["query_count"]
                measurements = []
                for _ in range(samples):
                    current.update(query_count=0, db_ms=0.0)
                    started = time.perf_counter()
                    response = await client.get(path)
                    total_ms = (time.perf_counter() - started) * 1000
                    measurements.append({
                        "status": response.status_code,
                        "query_count": current["query_count"],
                        "db_ms": round(current["db_ms"], 3),
                        "total_ms": round(total_ms, 3),
                        "response_bytes": len(response.content),
                    })
                output[name] = {
                    "path": path,
                    "cold_status": cold_response.status_code,
                    "cold_query_count": cold_query_count,
                    "warm_query_count": measurements[-1]["query_count"],
                    "median_db_ms": round(
                        statistics.median(row["db_ms"] for row in measurements), 3
                    ),
                    "median_total_ms": round(
                        statistics.median(row["total_ms"] for row in measurements), 3
                    ),
                    "response_bytes": measurements[-1]["response_bytes"],
                    "passed": (
                        cold_response.status_code == 200
                        and all(row["status"] == 200 for row in measurements)
                        and cold_query_count <= cold_limit
                        and measurements[-1]["query_count"] <= warm_limit
                    ),
                }
    finally:
        neo4j_service._execute = original_execute
        await neo4j_service.close()
    return output


def main() -> int:
    args = parse_args()
    database = inspect_database()
    benchmarks = asyncio.run(benchmark_endpoints(args.samples))
    profile_operators = {
        operator
        for profile in database["profiles"]
        for operator in profile["operators"]
    }
    passed = (
        not database["schema"]["missing_constraints"]
        and not database["schema"]["missing_indexes"]
        and not database["schema"]["offline_indexes"]
        and database["fulltext"]["count"] > 0
        and any("IndexSeek" in operator for operator in profile_operators)
        and all(result["passed"] for result in benchmarks.values())
    )
    report = {
        "passed": passed,
        "database": database,
        "benchmarks": benchmarks,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8", newline="\n")
    print(rendered)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
