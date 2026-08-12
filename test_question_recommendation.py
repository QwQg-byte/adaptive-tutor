"""Offline tests for graph-native question recommendations."""
import json
import unittest
from types import SimpleNamespace

import config
import graph_tools
import tutor_agent


class FakeQuestionGraph:
    def questions_of_knowledge(self, knowledge_id):
        return {
            "success": True,
            "message": "找到 1 道题目",
            "data": [
                {
                    "id": "Q/100",
                    "name": "二分查找练习",
                    "difficulty": "简单",
                    "url": "https://www.matiji.net/exam/brushquestion/100/1/1000",
                }
            ],
        }

    def search(self, keyword):
        return {
            "success": True,
            "data": [
                {
                    "id": "MC0218",
                    "name": "小码哥的开心数字",
                    "label": "Question",
                    "url": "https://www.matiji.net/exam/brushquestion/18/4446/example",
                }
            ],
        }


class FakeMessage:
    def __init__(self, *, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self, exclude_none=True):
        del exclude_none
        return {"role": "assistant", "content": self.content}


class FakeClient:
    def __init__(self, messages):
        self.messages = iter(messages)

    def chat(self, messages, tools, tool_choice):
        del messages, tools, tool_choice
        return next(self.messages)


class QuestionRecommendationTests(unittest.TestCase):
    def setUp(self):
        self.original_graph = graph_tools._graph
        self.original_frontend_url = config.GRAPH_FRONTEND_URL
        graph_tools._graph = FakeQuestionGraph()
        config.GRAPH_FRONTEND_URL = "http://127.0.0.1:5173/"

    def tearDown(self):
        graph_tools._graph = self.original_graph
        config.GRAPH_FRONTEND_URL = self.original_frontend_url

    def test_question_tool_returns_student_bound_graph_detail_url_only(self):
        result = json.loads(
            graph_tools.dispatch(
                "questions_of_knowledge",
                {"knowledge_id": "NODE_381"},
                student_id="student / 01",
            )
        )

        question = result["data"][0]
        self.assertEqual(
            question["detail_url"],
            "http://127.0.0.1:5173/questions?id=Q%2F100&student=student+%2F+01",
        )
        self.assertNotIn("url", question)
        self.assertNotIn("matiji.net", json.dumps(result, ensure_ascii=False))
        self.assertIn("记录做对/做错", result["presentation_instruction"])

    def test_system_prompt_requires_graph_detail_page(self):
        self.assertIn("必须先调 questions_of_knowledge", tutor_agent.SYSTEM)
        self.assertIn("detail_url", tutor_agent.SYSTEM)
        self.assertIn("绝不直接给码蹄集", tutor_agent.SYSTEM)

    def test_question_search_result_also_uses_internal_detail_page(self):
        result = json.loads(
            graph_tools.dispatch(
                "search_graph",
                {"keyword": "小码哥的开心数字"},
                student_id="student / 01",
            )
        )

        question = result["data"][0]
        self.assertEqual(
            question["detail_url"],
            "http://127.0.0.1:5173/questions?id=MC0218&student=student+%2F+01",
        )
        self.assertNotIn("url", question)
        self.assertNotIn("matiji.net", json.dumps(result, ensure_ascii=False))

    def test_agent_appends_matching_detail_link_when_model_omits_it(self):
        tool_call = SimpleNamespace(
            id="call-search",
            function=SimpleNamespace(
                name="search_graph",
                arguments=json.dumps({"keyword": "小码哥的开心数字"}, ensure_ascii=False),
            ),
        )
        client = FakeClient([
            FakeMessage(tool_calls=[tool_call]),
            FakeMessage(content="推荐题目：小码哥的开心数字（MC0218）。"),
        ])
        messages = [
            {"role": "system", "content": tutor_agent.SYSTEM},
            {"role": "user", "content": "给我推荐小码哥的开心数字这道题"},
        ]

        context = tutor_agent.TurnContext("student / 01")
        reply = tutor_agent.run_turn(
            client,
            messages,
            context=context,
        )

        self.assertEqual(context.tool_log, ["search_graph"])
        self.assertIn(
            "http://127.0.0.1:5173/questions?id=MC0218&student=student+%2F+01",
            reply,
        )
        self.assertIn("打开后可以标记", reply)


if __name__ == "__main__":
    unittest.main()
