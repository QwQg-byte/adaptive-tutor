"""Backward-compatible learner model backed by the unified state service."""

from __future__ import annotations

from pathlib import Path

from learning_state import LearningStateService


class LearnerModel:
    """Compatibility facade used by the tutor agent and diagnostic flow."""

    def __init__(self, db_path: str | Path | None = None):
        self.service = LearningStateService(db_path=db_path)
        self.db_path = self.service.db_path

    def record(
        self,
        student_id: str,
        node_id: str,
        node_name: str,
        correct: bool,
        kind: str = "practice",
        detail: str = "",
    ) -> float:
        return self.service.record_evidence(
            student_id, node_id, node_name, correct, kind=kind, detail=detail
        )

    def seed(
        self,
        student_id: str,
        node_id: str,
        node_name: str,
        value: float,
        detail: str = "diagnose_propagate",
    ) -> float:
        return self.service.seed(student_id, node_id, node_name, value, detail=detail)

    def note(self, student_id: str, detail: str, node_id: str | None = None) -> None:
        self.service.note(student_id, detail, node_id=node_id)

    def profile(self, student_id: str) -> dict:
        return self.service.profile(student_id)

    def mastered_ids(self, student_id: str) -> list[str]:
        return self.service.mastered_ids(student_id)

    def prunable_ids(self, student_id: str) -> list[str]:
        return self.service.prunable_ids(student_id)

    def history(
        self, student_id: str, node_id: str | None = None, limit: int = 20
    ) -> list[dict]:
        return self.service.history(student_id, node_id=node_id, limit=limit)
