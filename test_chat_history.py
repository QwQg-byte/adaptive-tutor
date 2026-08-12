"""Tests for restoring Tutor chat history after navigation or reload."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_server


class ChatHistoryTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(web_server.app)
        self.student = "history_test_student"
        web_server._sessions.pop(self.student, None)

    def tearDown(self):
        web_server._sessions.pop(self.student, None)

    def test_chat_history_restores_display_turns_and_reset_clears_them(self):
        with (
            patch.object(web_server.ta, "run_turn", return_value="站内题目链接：http://example.test/questions?id=1"),
            patch.object(web_server.graph_tools._learner, "profile", return_value={"nodes": []}),
        ):
            response = self.client.post(
                "/api/chat",
                json={"student": self.student, "message": "给我推荐一道题目"},
            )
        self.assertEqual(response.status_code, 200)

        history = self.client.get("/api/chat/history", params={"student": self.student})
        self.assertEqual(history.status_code, 200)
        self.assertEqual(
            history.json()["items"],
            [
                {"role": "user", "content": "给我推荐一道题目"},
                {
                    "role": "assistant",
                    "content": "站内题目链接：http://example.test/questions?id=1",
                    "tools": [],
                },
            ],
        )

        reset = self.client.post("/api/reset", params={"student": self.student})
        self.assertEqual(reset.status_code, 200)
        cleared = self.client.get("/api/chat/history", params={"student": self.student})
        self.assertEqual(cleared.json()["items"], [])

    def test_home_uses_configured_graph_frontend_url(self):
        with patch.object(
            web_server.config,
            "GRAPH_FRONTEND_URL",
            "http://graph.example.test/",
        ):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'const GRAPH_FRONTEND_URL = "http://graph.example.test/";',
            response.text,
        )
        self.assertNotIn("__GRAPH_FRONTEND_URL_JSON__", response.text)


if __name__ == "__main__":
    unittest.main()
