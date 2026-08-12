"""Phase 4 API contracts that do not require a live Neo4j instance."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


BACKEND_DIR = Path(__file__).resolve().parents[1] / "application" / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("NEO4J_PASSWORD", "unit-test-only-password")

from api.graph import get_knowledge_points_page  # noqa: E402


class Phase4ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_knowledge_page_returns_summaries_and_pagination(self):
        summary = {
            "id": "NODE_1",
            "node_id": "001",
            "name": "线性表",
            "node_type": "核心抽象",
            "chapter_id": 2,
            "section": "线性结构",
            "overview": "摘要",
            "type": "KnowledgeNode",
        }
        with patch(
            "api.graph.neo4j_service.execute_query",
            new=AsyncMock(side_effect=[[{"total": 31}], [summary]]),
        ) as execute_query:
            response = await get_knowledge_points_page(
                page=2,
                page_size=30,
                chapter_id=2,
                knowledge_type="核心抽象",
                keyword="线性",
            )

        self.assertTrue(response.success)
        self.assertEqual(response.data["items"], [summary])
        self.assertEqual(response.data["pagination"]["total_pages"], 2)
        list_parameters = execute_query.await_args_list[1].args[1]
        self.assertEqual(list_parameters["offset"], 30)
        self.assertEqual(list_parameters["keyword"], "线性")


if __name__ == "__main__":
    unittest.main()
