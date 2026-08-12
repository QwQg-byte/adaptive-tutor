"""Concurrency tests for request-local Tutor chat state."""

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from unittest.mock import patch

from fastapi.testclient import TestClient

import tutor_agent
import web_server


class ChatConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.students = {
            "concurrency_student_a",
            "concurrency_student_b",
            "concurrency_same_student",
            "concurrency_reset_student",
        }
        self._clear_students()

    def tearDown(self):
        self._clear_students()

    def _clear_students(self):
        with web_server._session_registry_lock:
            for student in self.students:
                web_server._sessions.pop(student, None)
                web_server._session_locks.pop(student, None)

    @staticmethod
    def _post(path, *, json=None, params=None):
        with TestClient(web_server.app) as client:
            return client.post(path, json=json, params=params)

    @staticmethod
    def _get(path, *, params=None):
        with TestClient(web_server.app) as client:
            return client.get(path, params=params)

    @staticmethod
    def _profile(student_id):
        return {"student_id": student_id, "nodes": []}

    def test_different_students_run_concurrently_without_context_leaks(self):
        barrier = threading.Barrier(2)

        def fake_run_turn(_client, messages, forced_tool=None, *, context):
            del _client, forced_tool
            barrier.wait(timeout=2)
            if context.student_id.endswith("_a"):
                context.record_tool("start_diagnostic")
            else:
                context.record_tool("get_student_profile")
            return f"reply:{context.student_id}:{messages[-1]['content']}"

        with (
            patch.object(web_server.ta, "run_turn", side_effect=fake_run_turn),
            patch.object(
                web_server.graph_tools._learner,
                "profile",
                side_effect=self._profile,
            ),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            futures = {
                student: executor.submit(
                    self._post,
                    "/api/chat",
                    json={"student": student, "message": f"message:{student}"},
                )
                for student in ("concurrency_student_a", "concurrency_student_b")
            }
            responses = {student: future.result(timeout=5) for student, future in futures.items()}

        student_a = responses["concurrency_student_a"].json()
        student_b = responses["concurrency_student_b"].json()
        self.assertEqual(student_a["tools"], ["start_diagnostic"])
        self.assertTrue(student_a["in_diagnostic"])
        self.assertEqual(student_b["tools"], ["get_student_profile"])
        self.assertFalse(student_b["in_diagnostic"])
        self.assertIn("concurrency_student_a", student_a["reply"])
        self.assertNotIn("concurrency_student_b", student_a["reply"])
        self.assertIn("concurrency_student_b", student_b["reply"])
        self.assertNotIn("concurrency_student_a", student_b["reply"])

        for student in ("concurrency_student_a", "concurrency_student_b"):
            history = self._get("/api/chat/history", params={"student": student}).json()
            contents = [item["content"] for item in history["items"]]
            self.assertTrue(all(student in content for content in contents))

    def test_same_student_chat_turns_are_serialized(self):
        student = "concurrency_same_student"
        first_entered = threading.Event()
        second_entered = threading.Event()
        release_first = threading.Event()
        state_lock = threading.Lock()
        active = 0
        max_active = 0
        calls = 0

        def fake_run_turn(_client, messages, forced_tool=None, *, context):
            nonlocal active, max_active, calls
            del _client, forced_tool
            with state_lock:
                calls += 1
                call_number = calls
                active += 1
                max_active = max(max_active, active)
            if call_number == 1:
                first_entered.set()
                self.assertTrue(release_first.wait(timeout=2))
            else:
                second_entered.set()
            text = messages[-1]["content"]
            context.record_tool(f"tool:{text}")
            with state_lock:
                active -= 1
            return f"reply:{text}"

        with (
            patch.object(web_server.ta, "run_turn", side_effect=fake_run_turn),
            patch.object(
                web_server.graph_tools._learner,
                "profile",
                side_effect=self._profile,
            ),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            first = executor.submit(
                self._post,
                "/api/chat",
                json={"student": student, "message": "first"},
            )
            self.assertTrue(first_entered.wait(timeout=2))
            second = executor.submit(
                self._post,
                "/api/chat",
                json={"student": student, "message": "second"},
            )
            self.assertFalse(second_entered.wait(timeout=0.15))
            release_first.set()
            self.assertEqual(first.result(timeout=5).status_code, 200)
            self.assertEqual(second.result(timeout=5).status_code, 200)

        self.assertEqual(max_active, 1)
        history = self._get("/api/chat/history", params={"student": student}).json()["items"]
        self.assertEqual(
            [(item["role"], item["content"]) for item in history],
            [
                ("user", "first"),
                ("assistant", "reply:first"),
                ("user", "second"),
                ("assistant", "reply:second"),
            ],
        )
        self.assertEqual(history[1]["tools"], ["tool:first"])
        self.assertEqual(history[3]["tools"], ["tool:second"])

    def test_reset_waits_for_active_turn_then_clears_session(self):
        student = "concurrency_reset_student"
        turn_entered = threading.Event()
        release_turn = threading.Event()

        def fake_run_turn(_client, messages, forced_tool=None, *, context):
            del _client, messages, forced_tool
            turn_entered.set()
            self.assertTrue(release_turn.wait(timeout=2))
            context.record_tool("get_student_profile")
            return "reply before reset"

        with (
            patch.object(web_server.ta, "run_turn", side_effect=fake_run_turn),
            patch.object(
                web_server.graph_tools._learner,
                "profile",
                side_effect=self._profile,
            ),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            chat = executor.submit(
                self._post,
                "/api/chat",
                json={"student": student, "message": "message before reset"},
            )
            self.assertTrue(turn_entered.wait(timeout=2))
            reset = executor.submit(
                self._post,
                "/api/reset",
                params={"student": student},
            )
            with self.assertRaises(TimeoutError):
                reset.result(timeout=0.15)
            release_turn.set()
            self.assertEqual(chat.result(timeout=5).status_code, 200)
            self.assertEqual(reset.result(timeout=5).json(), {"ok": True})

        history = self._get("/api/chat/history", params={"student": student}).json()
        self.assertEqual(history["items"], [])


class TurnContextTests(unittest.TestCase):
    def test_diagnostic_routing_uses_explicit_turn_state(self):
        self.assertEqual(
            tutor_agent.route_intent("这题做对了", in_diagnostic=True),
            "diagnose_answer",
        )
        self.assertEqual(
            tutor_agent.route_intent("这题做对了", in_diagnostic=False),
            "record_result",
        )

        context = tutor_agent.TurnContext("student")
        context.record_tool("start_diagnostic")
        self.assertTrue(context.in_diagnostic)
        context.record_tool("diagnose_answer")
        self.assertFalse(context.in_diagnostic)
        self.assertEqual(context.tool_log, ["start_diagnostic", "diagnose_answer"])


if __name__ == "__main__":
    unittest.main()
