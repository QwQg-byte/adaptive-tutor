"""Focused tests for the asynchronous Neo4j service contract."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


BACKEND_DIR = Path(__file__).resolve().parents[1] / "application" / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("NEO4J_PASSWORD", "unit-test-only-password")

from database.neo4j_exceptions import (  # noqa: E402
    Neo4jConnectionError,
    Neo4jQueryError,
    Neo4jQueryTimeoutError,
)
from database.neo4j_service import Neo4jService  # noqa: E402


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    async def data(self):
        return self.rows


class FakeTransaction:
    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error
        self.queries = []

    async def run(self, query, parameters):
        self.queries.append((query, parameters))
        if self.error is not None:
            raise self.error
        if not isinstance(query, str):
            raise TypeError("managed transaction requires a query string")
        return FakeResult(self.rows)


class FakeSession:
    def __init__(self, transaction):
        self.transaction = transaction

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute_read(self, callback):
        return await callback(self.transaction)

    async def execute_write(self, callback):
        return await callback(self.transaction)


class FakeDriver:
    def __init__(self, transaction):
        self.transaction = transaction

    def session(self, **kwargs):
        return FakeSession(self.transaction)


class Neo4jServiceTests(unittest.IsolatedAsyncioTestCase):
    def make_service(self, *, rows=None, error=None):
        service = Neo4jService()
        service.driver = FakeDriver(FakeTransaction(rows=rows, error=error))
        service._connected = True
        return service

    async def test_empty_result_is_not_an_error(self):
        service = self.make_service(rows=[])
        self.assertEqual(await service.execute_read("MATCH (n) RETURN n"), [])

    async def test_query_failure_is_explicit(self):
        service = self.make_service(error=ValueError("invalid cypher"))
        with self.assertRaises(Neo4jQueryError):
            await service.execute_read("invalid")

    async def test_timeout_has_specific_error(self):
        service = self.make_service(error=TimeoutError("too slow"))
        with self.assertRaises(Neo4jQueryTimeoutError):
            await service.execute_read("MATCH (n) RETURN n")

    async def test_not_connected_is_explicit(self):
        service = Neo4jService()
        service.driver = None
        service._connected = False
        with self.assertRaises(Neo4jConnectionError):
            await service.execute_read("RETURN 1")

    async def test_driver_creation_failure_is_mapped(self):
        service = Neo4jService()
        with patch(
            "database.neo4j_service.AsyncGraphDatabase.driver",
            side_effect=ValueError("invalid driver configuration"),
        ):
            with self.assertRaises(Neo4jConnectionError):
                await service.connect()

    async def test_statistics_use_one_query_and_cache(self):
        service = self.make_service(rows=[{
            "node_counts": [{"label": "KnowledgeNode", "count": 2}],
            "total_nodes": 2,
            "rel_counts": [{"type": "PREREQUISITE", "count": 1}],
            "total_relationships": 1,
        }])

        first = await service.get_statistics()
        second = await service.get_statistics()

        self.assertEqual(first, second)
        self.assertEqual(first["total_nodes"], 2)
        self.assertEqual(len(service.driver.transaction.queries), 1)

    def test_fulltext_query_preserves_cjk_and_escapes_operators(self):
        self.assertEqual(Neo4jService._fulltext_query("动态规划"), "动态规划")
        self.assertEqual(Neo4jService._fulltext_query("graph search"), "graph* AND search*")
        self.assertEqual(Neo4jService._fulltext_query("a+b"), "a\\+b")

    def test_search_keyword_normalizes_binary_search_synonym(self):
        self.assertEqual(Neo4jService._normalize_search_keyword("折半查找"), "二分查找")
        self.assertEqual(Neo4jService._normalize_search_keyword(" 二分查找 "), "二分查找")
        self.assertEqual(Neo4jService._normalize_search_keyword("折半"), "折半")

    def test_difficulty_node_display_name_uses_level(self):
        self.assertEqual(
            Neo4jService._node_display_name(
                "Difficulty",
                {"id": "DIFF_星耀", "level": "星耀"},
            ),
            "星耀",
        )
        self.assertEqual(
            Neo4jService._node_display_name(
                "Difficulty",
                {"id": "DIFF_简单"},
            ),
            "Difficulty",
        )

    async def test_fulltext_search_returns_rank_score(self):
        service = self.make_service(rows=[{
            "id": "NODE_1",
            "label": "KnowledgeNode",
            "properties": {"name": "动态规划"},
            "score": 2.5,
        }])

        rows = await service.search_nodes("动态规划", limit=5)

        self.assertEqual(rows[0]["search_score"], 2.5)
        query = service.driver.transaction.queries[0][0]
        self.assertIn("db.index.fulltext.queryNodes", query)

    async def test_shortest_path_restricts_labels_and_relationship_types(self):
        service = self.make_service(rows=[])

        self.assertIsNone(await service.find_shortest_path("NODE_1", "NODE_2", 4))

        query = service.driver.transaction.queries[0][0]
        self.assertIn("MATCH (start:KnowledgeNode)", query)
        self.assertIn(":PREREQUISITE|RELATED_TO", query)
        self.assertNotIn("-[*", query)

    async def test_graph_data_prioritizes_chapter_and_relationship_context(self):
        service = Neo4jService()
        service.execute_read = AsyncMock(side_effect=[
            [{
                "id": "CHAP_16",
                "element_id": "4:16",
                "label": "Chapter",
                "properties": {"name": "分治法", "order": 16},
            }],
            [],
        ])
        service.get_statistics = AsyncMock(return_value={
            "nodes": {"Chapter": 24, "KnowledgeNode": 444},
            "total_nodes": 468,
            "relationships": {"BELONGS_TO": 444},
            "total_relationships": 444,
            "labels": ["Chapter", "KnowledgeNode"],
            "relationship_types": ["BELONGS_TO"],
        })

        graph = await service.get_graph_data(limit=77)

        self.assertEqual(graph["nodes"][0]["type"], "Chapter")
        self.assertEqual(len(service.execute_read.await_args_list), 2)
        node_query = service.execute_read.await_args_list[0].args[0]
        self.assertIn("chapter_representatives", node_query)
        self.assertIn("relationship_representatives", node_query)
        self.assertIn("difficulty_context", node_query)
        self.assertLess(
            node_query.index("WHEN n IN chapter_representatives THEN 1"),
            node_query.index("WHEN n:KnowledgeNode THEN 5"),
        )
        relationship_parameters = service.execute_read.await_args_list[1].args[1]
        self.assertEqual(relationship_parameters["element_ids"], ["4:16"])

    async def test_node_neighbors_returns_bounded_graph_fragment(self):
        service = self.make_service(rows=[{
            "neighbor_id": "NODE_2",
            "neighbor_name": "链表",
            "neighbor_type": "KnowledgeNode",
            "neighbor_properties": {"name": "链表"},
            "from_id": "NODE_1",
            "to_id": "NODE_2",
            "relationship_type": "PREREQUISITE",
            "relationship_properties": {"weight": 1},
        }])

        fragment = await service.get_node_neighbors(
            "NODE_1", limit=10, relationship_types=["PREREQUISITE"]
        )

        self.assertEqual(fragment["nodes"][0]["id"], "NODE_2")
        self.assertEqual(fragment["edges"][0]["from"], "NODE_1")
        query, parameters = service.driver.transaction.queries[0]
        self.assertIn("type(r) IN $relationship_types", query)
        self.assertEqual(parameters["limit"], 10)
        self.assertEqual(parameters["relationship_types"], ["PREREQUISITE"])

    async def test_graph_fragment_loads_requested_nodes_and_internal_edges(self):
        service = Neo4jService()
        service.execute_read = AsyncMock(side_effect=[
            [
                {
                    "id": "NODE_1",
                    "element_id": "4:1",
                    "label": "KnowledgeNode",
                    "properties": {"name": "数据"},
                },
                {
                    "id": "NODE_2",
                    "element_id": "4:2",
                    "label": "KnowledgeNode",
                    "properties": {"name": "线性表"},
                },
            ],
            [{
                "from": "NODE_2",
                "to": "NODE_1",
                "label": "PREREQUISITE",
                "properties": {"weight": 1},
            }],
        ])

        fragment = await service.get_graph_fragment(
            ["NODE_1", "NODE_2", "NODE_MISSING"],
            relationship_types=["PREREQUISITE"],
        )

        self.assertEqual(len(fragment["nodes"]), 2)
        self.assertEqual(fragment["edges"][0]["label"], "PREREQUISITE")
        self.assertEqual(fragment["missing_node_ids"], ["NODE_MISSING"])
        edge_parameters = service.execute_read.await_args_list[1].args[1]
        self.assertEqual(edge_parameters["element_ids"], ["4:1", "4:2"])
        self.assertEqual(edge_parameters["relationship_types"], ["PREREQUISITE"])


if __name__ == "__main__":
    unittest.main()
