"""Focused contracts for the phase 3 API query rewrites."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException


BACKEND_DIR = Path(__file__).resolve().parents[1] / "application" / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("NEO4J_PASSWORD", "unit-test-only-password")

from api import graph  # noqa: E402


class Phase3QueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_knowledge_detail_is_loaded_in_one_query(self):
        execute = AsyncMock(return_value=[{
            "id": "NODE_1",
            "type": "KnowledgeNode",
            "properties": {"name": "示例"},
            "related_nodes": [],
            "chapter_info": None,
        }])

        with patch.object(graph.neo4j_service, "execute_query", execute):
            response = await graph.get_knowledge_point_detail("NODE_1")

        self.assertTrue(response.success)
        self.assertEqual(execute.await_count, 1)
        self.assertIn("OPTIONAL MATCH", execute.await_args.args[0])

    async def test_home_data_uses_one_query_without_rand_sort(self):
        execute = AsyncMock(return_value=[{
            "total_questions": 1,
            "total_knowledge_points": 2,
            "total_chapters": 3,
            "total_relationships": 4,
            "difficulty_stats": [],
            "category_stats": [],
            "hot_knowledge_points": [],
            "recommended_questions": [],
        }])

        with patch.object(graph.neo4j_service, "execute_query", execute):
            response = await graph.get_home_data()

        self.assertTrue(response.success)
        self.assertEqual(execute.await_count, 1)
        self.assertNotIn("rand()", execute.await_args.args[0])

    async def test_question_page_limits_before_counting_relationships(self):
        execute = AsyncMock(side_effect=[
            [{"total": 1}],
            [{
                "id": "MT1001",
                "name": "题目",
                "difficulty": "简单",
                "url": "",
                "category1": "算法基础",
                "category2": "",
                "source": "码蹄集",
                "kp_count": 2,
            }],
        ])

        with patch.object(graph.neo4j_service, "execute_query", execute):
            response = await graph.get_questions(
                page=1,
                page_size=20,
                difficulty=None,
                category1=None,
                keyword=None,
                sort_by="id",
                after_id=None,
            )

        list_query = execute.await_args_list[1].args[0]
        self.assertLess(list_query.index("SKIP $skip"), list_query.index("OPTIONAL MATCH"))
        self.assertEqual(response.data["pagination"]["next_cursor"], None)

    async def test_deep_offset_requires_cursor(self):
        with self.assertRaises(HTTPException) as context:
            await graph.get_questions(
                page=1000,
                page_size=20,
                difficulty=None,
                category1=None,
                keyword=None,
                sort_by="id",
                after_id=None,
            )

        self.assertEqual(context.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
