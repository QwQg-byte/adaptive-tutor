import json
import sqlite3
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

import web_server
from learning_state import LearningStateService, RevisionConflict


class FakeGraph:
    knowledge: ClassVar[list[dict[str, object]]] = [
        {"id": "NODE_BASE", "name": "基础", "chapter_id": 1},
        {"id": "NODE_TARGET", "name": "目标", "chapter_id": 1},
        {"id": "NODE_OTHER", "name": "其他", "chapter_id": 2},
    ]

    def list_knowledge_points(self, limit=2000):
        return {"data": self.knowledge[:limit]}

    def generate_plan(
        self,
        target,
        mastered=None,
        completed=None,
        difficulty_preference="balanced",
        questions_per_step=3,
        max_depth=6,
    ):
        target_id = "NODE_OTHER" if target in {"其他", "NODE_OTHER"} else "NODE_TARGET"
        candidates = [
            {
                "order": 1,
                "id": "NODE_BASE",
                "name": "基础",
                "questions": [{"id": "Q_BASE", "name": "基础题"}],
            },
            {
                "order": 2,
                "id": target_id,
                "name": "其他" if target_id == "NODE_OTHER" else "目标",
                "questions": [{"id": "Q_TARGET", "name": "目标题"}],
                "is_target": True,
            },
        ]
        mastered = set(mastered or [])
        completed = set(completed or [])
        if target_id in mastered:
            return {
                "data": {
                    "target": {"id": target_id, "name": candidates[-1]["name"]},
                    "steps": [],
                    "total_steps": 0,
                    "mastered_skipped": [],
                    "completed_skipped": [],
                    "already_mastered": True,
                    "already_completed": False,
                    "difficulty_preference": difficulty_preference,
                }
            }
        if target_id in completed:
            return {
                "data": {
                    "target": {"id": target_id, "name": candidates[-1]["name"]},
                    "steps": [],
                    "total_steps": 0,
                    "mastered_skipped": [],
                    "completed_skipped": [],
                    "already_mastered": False,
                    "already_completed": True,
                    "difficulty_preference": difficulty_preference,
                }
            }
        steps = [step for step in candidates if step["id"] not in mastered | completed]
        return {
            "data": {
                "target": {"id": target_id, "name": candidates[-1]["name"]},
                "steps": steps,
                "total_steps": len(steps),
                "mastered_skipped": [
                    {"id": step["id"], "name": step["name"]}
                    for step in candidates
                    if step["id"] in mastered
                ],
                "completed_skipped": [
                    {"id": step["id"], "name": step["name"]}
                    for step in candidates
                    if step["id"] in completed
                ],
                "difficulty_preference": difficulty_preference,
                "already_mastered": False,
                "already_completed": False,
            }
        }

    def knowledge_of_question(self, question_id):
        if question_id == "Q_OTHER":
            return {"data": [{"id": "NODE_OTHER", "name": "其他", "weight": 1.0}]}
        if question_id == "Q_TARGET":
            return {
                "data": [
                    {"id": "NODE_TARGET", "name": "目标", "weight": 0.9},
                    {"id": "NODE_BASE", "name": "基础", "weight": 0.5},
                ]
            }
        return {"data": [{"id": "NODE_BASE", "name": "基础", "weight": 1.0}]}


class BrokenGraph(FakeGraph):
    def generate_plan(self, *args, **kwargs):
        raise ConnectionError("offline")


@pytest.fixture
def service(tmp_path):
    return LearningStateService(tmp_path / "learner.db", graph=FakeGraph())


def test_migration_upgrades_existing_database_without_losing_mastery(tmp_path):
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE mastery (
            student_id TEXT NOT NULL, node_id TEXT NOT NULL, node_name TEXT,
            mastery REAL NOT NULL, attempts INTEGER NOT NULL, correct INTEGER NOT NULL,
            updated_at REAL NOT NULL, PRIMARY KEY(student_id,node_id)
        );
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL, node_id TEXT,
            kind TEXT NOT NULL, correct INTEGER, detail TEXT, created_at REAL NOT NULL
        );
        INSERT INTO mastery VALUES('s1','NODE_OLD','旧知识',0.8,3,3,1.0);
        """
    )
    connection.commit()
    connection.close()

    migrated = LearningStateService(db_path, graph=FakeGraph())

    assert migrated.profile("s1")["nodes"][0]["node_id"] == "NODE_OLD"
    assert migrated.profile("s1")["nodes"][0]["mastery_state"] == "assessed_mastery"
    with sqlite3.connect(db_path) as check:
        columns = {row[1] for row in check.execute("PRAGMA table_info(mastery)")}
        tables = {row[0] for row in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"evidence_source", "manual_override", "revision"} <= columns
    assert {"plan_progress", "question_attempts", "mistake_items", "learner_state_meta"} <= tables


def test_manual_override_is_idempotent_and_revision_checked(service):
    first = service.set_manual_override("s1", "NODE_BASE", "mastered", 0, "manual-key-0001")
    replay = service.set_manual_override("s1", "NODE_BASE", "mastered", 0, "manual-key-0001")

    assert first["revision"] == 1
    assert replay["revision"] == 1
    assert replay["idempotent"] is True
    with pytest.raises(RevisionConflict) as conflict:
        service.set_manual_override("s1", "NODE_TARGET", "learning", 0, "manual-key-0002")
    assert conflict.value.current_revision == 1


def test_plan_progress_is_isolated_by_target(service):
    target_plan = service.generate_plan("s1", "目标", expected_revision=0)
    updated = service.set_plan_step(
        "s1", "NODE_TARGET", "NODE_BASE", "completed", 0, "step-key-target"
    )
    other_plan = service.generate_plan("s1", "其他", expected_revision=updated["revision"])

    assert [step["id"] for step in service.generate_plan("s1", "目标")["steps"]] == [
        "NODE_TARGET"
    ]
    assert "NODE_BASE" in [step["id"] for step in other_plan["steps"]]
    assert target_plan["target_id"] == "NODE_TARGET"


def test_soft_confidence_prunes_prerequisite_but_never_the_explicit_target(service):
    service.seed("s1", "NODE_BASE", "基础", 0.55)
    service.seed("s1", "NODE_TARGET", "目标", 0.55)

    plan = service.generate_plan("s1", "目标", expected_revision=2)

    assert plan["already_mastered"] is False
    assert [step["id"] for step in plan["steps"]] == ["NODE_TARGET"]
    assert plan["target_mastery_state"] == "soft_confidence"
    assert plan["target_manual_override"] is None
    assert any(
        item["id"] == "NODE_BASE" and item["reason"] == "soft_confidence"
        for item in plan["skipped"]
    )


def test_only_real_or_self_reported_mastery_can_skip_the_explicit_target(service):
    manual = service.set_manual_override(
        "s1", "NODE_TARGET", "mastered", 0, "target-manual-mastered"
    )

    plan = service.generate_plan("s1", "目标", expected_revision=manual["revision"])

    assert plan["already_mastered"] is True
    assert plan["target_mastery_state"] == "self_reported_mastery"
    assert plan["target_manual_override"] == "mastered"


def test_dashboard_does_not_recommend_a_completed_target(service):
    service.seed("s1", "NODE_TARGET", "目标", 0.55)
    service.generate_plan("s1", "目标", expected_revision=1)
    service.set_plan_step(
        "s1", "NODE_TARGET", "NODE_TARGET", "completed", 1, "complete-target"
    )

    dashboard = service.dashboard("s1")

    assert dashboard["recommendation"]["id"] != "NODE_TARGET"


def test_completed_soft_target_can_be_reopened_and_planned(service):
    service.seed("s1", "NODE_TARGET", "目标", 0.55)
    service.generate_plan("s1", "目标", expected_revision=1)
    completed = service.set_plan_step(
        "s1", "NODE_TARGET", "NODE_TARGET", "completed", 1, "complete-soft-target"
    )
    completed_plan = service.generate_plan(
        "s1", "目标", expected_revision=completed["revision"]
    )
    reopened = service.set_plan_step(
        "s1",
        "NODE_TARGET",
        "NODE_TARGET",
        "in_progress",
        completed["revision"],
        "reopen-soft-target",
    )
    reopened_plan = service.generate_plan(
        "s1", "目标", expected_revision=reopened["revision"]
    )

    assert completed_plan["already_completed"] is True
    assert reopened_plan["already_completed"] is False
    assert any(step["id"] == "NODE_TARGET" for step in reopened_plan["steps"])


def test_attempt_updates_one_primary_node_and_resolves_mistake(service):
    service.generate_plan("s1", "目标", expected_revision=0)
    wrong = service.record_attempt(
        "s1",
        "Q_TARGET",
        False,
        "graph",
        0,
        "attempt-key-wrong",
        target_id="NODE_TARGET",
        path_node_id="NODE_TARGET",
    )
    replay = service.record_attempt(
        "s1",
        "Q_TARGET",
        False,
        "graph",
        0,
        "attempt-key-wrong",
        target_id="NODE_TARGET",
        path_node_id="NODE_TARGET",
    )
    correct = service.record_attempt(
        "s1",
        "Q_TARGET",
        True,
        "graph",
        wrong["revision"],
        "attempt-key-correct",
        target_id="NODE_TARGET",
        path_node_id="NODE_TARGET",
    )

    assert wrong["revision"] == replay["revision"] == 1
    assert replay["idempotent"] is True
    assert wrong["attribution"][0]["node_id"] == "NODE_TARGET"
    assert service.profile("s1")["nodes"][0]["node_id"] == "NODE_TARGET"
    assert correct["mistake"]["status"] == "resolved"
    assert correct["mistake"]["wrong_count"] == 1
    assert correct["mistake"]["correct_after_wrong_count"] == 1


def test_local_v1_import_preserves_measured_mastery_and_is_idempotent(service):
    service.record_evidence("s1", "NODE_BASE", "基础", True)
    payload = {
        "version": 1,
        "mastered": {"NODE_BASE": {"source": "manual"}, "NODE_OTHER": {}},
        "progress": {},
        "plan_done": {"NODE_TARGET": {"NODE_BASE": "2026-08-01T10:00:00"}},
        "mistakes": {
            "Q_BASE": {
                "wrong_count": 3,
                "unresolved": True,
                "knowledge_ids": ["NODE_BASE"],
            }
        },
    }
    first = service.import_local_v1("s1", payload, expected_revision=1)
    replay = service.import_local_v1("s1", payload, expected_revision=1)

    base = next(node for node in service.profile("s1")["nodes"] if node["node_id"] == "NODE_BASE")
    assert base["mastery"] == pytest.approx(0.4)
    assert base["attempts"] == 1
    assert base["manual_override"] == "mastered"
    assert first["revision"] == 2
    assert replay["revision"] == 2
    assert replay["idempotent"] is True
    assert service.state("s1")["mistake_summary"]["wrong_attempts"] == 3


def test_api_rejects_forged_mastered_and_returns_revision_conflict(service, monkeypatch):
    monkeypatch.setattr(web_server, "_learning", service)
    client = TestClient(web_server.app)

    forged = client.post(
        "/api/learners/s1/plans",
        json={"target": "目标", "mastered": ["NODE_BASE"]},
    )
    assert forged.status_code == 422
    assert forged.json()["error"]["code"] == "validation_error"

    first = client.patch(
        "/api/learners/s1/knowledge/NODE_BASE",
        json={
            "manual_override": "mastered",
            "expected_revision": 0,
            "idempotency_key": "api-manual-key-1",
        },
    )
    stale = client.patch(
        "/api/learners/s1/knowledge/NODE_TARGET",
        json={
            "manual_override": "learning",
            "expected_revision": 0,
            "idempotency_key": "api-manual-key-2",
        },
    )
    assert first.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["error"] == {
        "code": "revision_conflict",
        "message": "学习状态已更新，当前版本为 1",
        "current_revision": 1,
    }


def test_api_views_share_revision_and_graph_failure_is_stable(service, monkeypatch, tmp_path):
    monkeypatch.setattr(web_server, "_learning", service)
    client = TestClient(web_server.app)
    state = client.get("/api/learners/s1/state").json()
    mistakes = client.get("/api/learners/s1/mistakes").json()
    plan = client.post(
        "/api/learners/s1/plans",
        json={"target": "目标", "expected_revision": state["revision"]},
    ).json()

    assert state["revision"] == mistakes["revision"] == plan["revision"]

    broken = LearningStateService(tmp_path / "broken.db", graph=BrokenGraph())
    monkeypatch.setattr(web_server, "_learning", broken)
    unavailable = client.post(
        "/api/learners/s1/plans",
        json={"target": "目标", "expected_revision": 0},
    )
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "graph_unavailable"


def test_local_import_report_is_json_serializable(service):
    report = service.import_local_v1(
        "s1",
        {"version": 1, "mastered": {}, "progress": {}, "mistakes": {}, "plan_done": {}},
    )
    json.dumps(report)


def test_import_preview_has_no_database_side_effects(service):
    report = service.import_local_v1(
        "preview-student",
        {
            "version": 1,
            "mastered": {"NODE_BASE": {}},
            "progress": {},
            "mistakes": {},
            "plan_done": {},
        },
        preview=True,
    )

    assert report["preview"] is True
    assert report["summary"]["mastered"] == 1
    with sqlite3.connect(service.db_path) as connection:
        meta = connection.execute(
            "SELECT 1 FROM learner_state_meta WHERE student_id='preview-student'"
        ).fetchone()
    assert meta is None


def test_mistake_reopens_and_plan_receives_review_task(service):
    service.generate_plan("s1", "目标", expected_revision=0)
    wrong = service.record_attempt(
        "s1", "Q_TARGET", False, "graph", 0, "reopen-wrong-1",
        target_id="NODE_TARGET", path_node_id="NODE_TARGET"
    )
    plan_with_review = service.generate_plan(
        "s1", "目标", expected_revision=wrong["revision"]
    )
    correct = service.record_attempt(
        "s1", "Q_TARGET", True, "graph", wrong["revision"], "reopen-correct",
        target_id="NODE_TARGET", path_node_id="NODE_TARGET"
    )
    reopened = service.record_attempt(
        "s1", "Q_TARGET", False, "graph", correct["revision"], "reopen-wrong-2",
        target_id="NODE_TARGET", path_node_id="NODE_TARGET"
    )

    target_step = next(step for step in plan_with_review["steps"] if step["id"] == "NODE_TARGET")
    assert target_step["mistake_count"] == 1
    assert target_step["review_tasks"][0]["question_id"] == "Q_TARGET"
    assert reopened["mistake"]["status"] == "open"
    assert reopened["mistake"]["wrong_count"] == 2
    assert len(service.history("s1")) == 3


def test_unrelated_mistake_stays_global_and_does_not_change_target_plan(service):
    wrong = service.record_attempt(
        "s1", "Q_OTHER", False, "graph", 0, "unrelated-wrong"
    )
    plan = service.generate_plan(
        "s1", "目标", expected_revision=wrong["revision"]
    )

    assert any(item["question_id"] == "Q_OTHER" for item in service.mistakes("s1")["items"])
    assert plan["review_before_plan"] == []
    assert all(step["review_tasks"] == [] for step in plan["steps"])
    assert [step["id"] for step in plan["steps"]] == ["NODE_BASE", "NODE_TARGET"]


def test_manual_review_does_not_change_mastery(service):
    service.generate_plan("s1", "目标", expected_revision=0)
    wrong = service.record_attempt(
        "s1", "Q_TARGET", False, "graph", 0, "manual-review-wrong",
        target_id="NODE_TARGET", path_node_id="NODE_TARGET"
    )
    before = service.profile("s1")["nodes"][0]["mastery"]
    resolved = service.resolve_mistake(
        "s1", "Q_TARGET", "manual_review", wrong["revision"], "manual-review-resolve"
    )
    after = service.profile("s1")["nodes"][0]["mastery"]

    assert resolved["status"] == "resolved"
    assert after == before
