"""Unified learner-state storage and orchestration.

SQLite owns learner facts. Neo4j remains a stateless source of knowledge,
questions, and learning-path topology.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import config

SCHEMA_VERSION = 1
EMA_ALPHA = 0.4


class LearningStateError(Exception):
    """Base class for stable learner API errors."""


class RevisionConflict(LearningStateError):
    def __init__(self, current_revision: int):
        super().__init__(f"学习状态已更新，当前版本为 {current_revision}")
        self.current_revision = current_revision


class LearningTargetNotFound(LearningStateError):
    pass


class InvalidLearningContext(LearningStateError):
    pass


class GraphUnavailable(LearningStateError):
    pass


def _timestamp(value: Any, fallback: float | None = None) -> float:
    if isinstance(value, (int, float)):
        number = float(value)
        return number / 1000 if number > 10_000_000_000 else number
    if isinstance(value, str) and value:
        try:
            return float(value)
        except ValueError:
            try:
                return time.mktime(time.strptime(value[:19], "%Y-%m-%dT%H:%M:%S"))
            except ValueError:
                pass
    return time.time() if fallback is None else fallback


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _unwrap_graph(response: Any) -> Any:
    if isinstance(response, dict) and "data" in response:
        return response["data"]
    return response


class LearningStateService:
    """Transactional service for mastery, plans, attempts, and mistakes."""

    def __init__(self, db_path: str | Path | None = None, graph: Any = None):
        self.db_path = str(db_path or config.LEARNER_DB)
        self.graph = graph
        self.migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
        return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}

    @classmethod
    def _add_column(cls, connection: sqlite3.Connection, table: str, definition: str) -> None:
        name = definition.split()[0]
        if name not in cls._columns(connection, table):
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")

    def migrate(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._write() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mastery (
                    student_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    node_name TEXT,
                    mastery REAL NOT NULL DEFAULT 0.0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    correct INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL,
                    evidence_source TEXT NOT NULL DEFAULT 'practice',
                    manual_override TEXT,
                    revision INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (student_id, node_id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT NOT NULL,
                    node_id TEXT,
                    kind TEXT NOT NULL,
                    correct INTEGER,
                    detail TEXT,
                    created_at REAL NOT NULL,
                    question_id TEXT,
                    target_id TEXT,
                    path_node_id TEXT,
                    idempotency_key TEXT,
                    source_page TEXT,
                    revision INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            for definition in (
                "evidence_source TEXT NOT NULL DEFAULT 'practice'",
                "manual_override TEXT",
                "revision INTEGER NOT NULL DEFAULT 0",
            ):
                self._add_column(connection, "mastery", definition)
            for definition in (
                "question_id TEXT",
                "target_id TEXT",
                "path_node_id TEXT",
                "idempotency_key TEXT",
                "source_page TEXT",
                "revision INTEGER NOT NULL DEFAULT 0",
            ):
                self._add_column(connection, "events", definition)

            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_events_student
                    ON events(student_id, created_at DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_events_idempotency
                    ON events(student_id, idempotency_key)
                    WHERE idempotency_key IS NOT NULL;

                CREATE TABLE IF NOT EXISTS learner_state_meta (
                    student_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL DEFAULT 0,
                    local_v1_imported INTEGER NOT NULL DEFAULT 0,
                    local_v1_hash TEXT,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS plan_progress (
                    student_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('in_progress', 'completed')),
                    completed_at REAL,
                    updated_at REAL NOT NULL,
                    revision INTEGER NOT NULL,
                    PRIMARY KEY (student_id, target_id, node_id)
                );
                CREATE INDEX IF NOT EXISTS idx_plan_progress_student_target
                    ON plan_progress(student_id, target_id);

                CREATE TABLE IF NOT EXISTS question_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    student_id TEXT NOT NULL,
                    question_id TEXT NOT NULL,
                    target_id TEXT,
                    path_node_id TEXT,
                    correct INTEGER NOT NULL,
                    source_page TEXT NOT NULL,
                    attempted_at REAL NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    UNIQUE(student_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_attempts_student_question
                    ON question_attempts(student_id, question_id, attempted_at DESC);
                CREATE TABLE IF NOT EXISTS attempt_knowledge (
                    attempt_id TEXT NOT NULL REFERENCES question_attempts(attempt_id) ON DELETE CASCADE,
                    node_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('primary', 'supporting')),
                    weight REAL NOT NULL,
                    PRIMARY KEY (attempt_id, node_id)
                );
                CREATE TABLE IF NOT EXISTS mistake_items (
                    student_id TEXT NOT NULL,
                    question_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('open', 'resolved')),
                    resolution TEXT,
                    wrong_count INTEGER NOT NULL DEFAULT 0,
                    correct_after_wrong_count INTEGER NOT NULL DEFAULT 0,
                    last_wrong_at REAL,
                    resolved_at REAL,
                    updated_at REAL NOT NULL,
                    revision INTEGER NOT NULL,
                    PRIMARY KEY (student_id, question_id)
                );
                CREATE INDEX IF NOT EXISTS idx_mistakes_student_status
                    ON mistake_items(student_id, status, updated_at DESC);

                CREATE TABLE IF NOT EXISTS issued_plan_steps (
                    student_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    question_ids TEXT NOT NULL DEFAULT '[]',
                    issued_at REAL NOT NULL,
                    state_revision INTEGER NOT NULL,
                    PRIMARY KEY (student_id, target_id, node_id)
                );
                CREATE TABLE IF NOT EXISTS node_activity (
                    student_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    mastery_hint REAL NOT NULL DEFAULT 0,
                    last_seen_at REAL,
                    updated_at REAL NOT NULL,
                    revision INTEGER NOT NULL,
                    PRIMARY KEY (student_id, node_id)
                );
                CREATE TABLE IF NOT EXISTS state_idempotency (
                    student_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (student_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS local_imports (
                    student_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    imported_at REAL NOT NULL,
                    PRIMARY KEY (student_id, content_hash)
                );
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(?, ?)",
                (SCHEMA_VERSION, time.time()),
            )

    @staticmethod
    def _ensure_meta(connection: sqlite3.Connection, student_id: str) -> None:
        connection.execute(
            "INSERT OR IGNORE INTO learner_state_meta(student_id, revision, updated_at) VALUES(?,0,?)",
            (student_id, time.time()),
        )

    @classmethod
    def _revision(cls, connection: sqlite3.Connection, student_id: str) -> int:
        cls._ensure_meta(connection, student_id)
        row = connection.execute(
            "SELECT revision FROM learner_state_meta WHERE student_id=?", (student_id,)
        ).fetchone()
        return int(row["revision"])

    @classmethod
    def _check_revision(
        cls, connection: sqlite3.Connection, student_id: str, expected_revision: int | None
    ) -> int:
        current = cls._revision(connection, student_id)
        if expected_revision is not None and expected_revision != current:
            raise RevisionConflict(current)
        return current

    @staticmethod
    def _next_revision(connection: sqlite3.Connection, student_id: str, current: int) -> int:
        revision = current + 1
        connection.execute(
            "UPDATE learner_state_meta SET revision=?, updated_at=? WHERE student_id=?",
            (revision, time.time(), student_id),
        )
        return revision

    @staticmethod
    def _idempotent_result(
        connection: sqlite3.Connection, student_id: str, key: str | None, operation: str
    ) -> dict | None:
        if not key:
            return None
        row = connection.execute(
            "SELECT operation,result_json FROM state_idempotency "
            "WHERE student_id=? AND idempotency_key=?",
            (student_id, key),
        ).fetchone()
        if row is None:
            return None
        if row["operation"] != operation:
            raise InvalidLearningContext("幂等键已被其他操作使用")
        result = json.loads(row["result_json"])
        result["idempotent"] = True
        return result

    @staticmethod
    def _save_idempotent_result(
        connection: sqlite3.Connection,
        student_id: str,
        key: str | None,
        operation: str,
        result: dict,
    ) -> None:
        if key:
            connection.execute(
                "INSERT INTO state_idempotency(student_id,idempotency_key,operation,result_json,created_at) "
                "VALUES(?,?,?,?,?)",
                (student_id, key, operation, _json(result), time.time()),
            )

    @staticmethod
    def _mastery_state(row: dict | sqlite3.Row) -> str:
        manual = row["manual_override"]
        mastery = float(row["mastery"])
        attempts = int(row["attempts"])
        if manual == "mastered":
            return "self_reported_mastery"
        if attempts > 0 and mastery >= config.MASTERY_THRESHOLD:
            return "assessed_mastery"
        if attempts == 0 and mastery >= config.PRUNE_THRESHOLD:
            return "soft_confidence"
        if attempts > 0 or mastery > 0 or manual == "learning":
            return "weak"
        return "untested"

    @classmethod
    def _mastery_dict(cls, row: sqlite3.Row) -> dict:
        result = dict(row)
        result["mastery"] = float(result["mastery"])
        result["mastery_state"] = cls._mastery_state(result)
        result["prunable"] = (
            result["mastery"] >= config.PRUNE_THRESHOLD
            or result["manual_override"] == "mastered"
        )
        return result

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        *,
        student_id: str,
        kind: str,
        revision: int,
        node_id: str | None = None,
        correct: bool | None = None,
        detail: str = "",
        question_id: str | None = None,
        target_id: str | None = None,
        path_node_id: str | None = None,
        idempotency_key: str | None = None,
        source_page: str | None = None,
    ) -> None:
        connection.execute(
            "INSERT INTO events(student_id,node_id,kind,correct,detail,created_at,question_id,"
            "target_id,path_node_id,idempotency_key,source_page,revision) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                student_id,
                node_id,
                kind,
                None if correct is None else int(correct),
                detail,
                time.time(),
                question_id,
                target_id,
                path_node_id,
                idempotency_key,
                source_page,
                revision,
            ),
        )

    @staticmethod
    def _apply_evidence(
        connection: sqlite3.Connection,
        student_id: str,
        node_id: str,
        node_name: str,
        correct: bool,
        source: str,
        revision: int,
    ) -> float:
        row = connection.execute(
            "SELECT mastery,attempts,correct FROM mastery WHERE student_id=? AND node_id=?",
            (student_id, node_id),
        ).fetchone()
        signal = 1.0 if correct else 0.0
        now = time.time()
        if row is None:
            mastery = signal * EMA_ALPHA
            connection.execute(
                "INSERT INTO mastery(student_id,node_id,node_name,mastery,attempts,correct,updated_at,"
                "evidence_source,revision) VALUES(?,?,?,?,1,?,?,?,?)",
                (student_id, node_id, node_name, mastery, int(correct), now, source, revision),
            )
        else:
            mastery = (1 - EMA_ALPHA) * float(row["mastery"]) + EMA_ALPHA * signal
            connection.execute(
                "UPDATE mastery SET node_name=COALESCE(NULLIF(?,''),node_name),mastery=?,"
                "attempts=attempts+1,correct=correct+?,updated_at=?,evidence_source=?,revision=? "
                "WHERE student_id=? AND node_id=?",
                (node_name, mastery, int(correct), now, source, revision, student_id, node_id),
            )
        return mastery

    def record_evidence(
        self,
        student_id: str,
        node_id: str,
        node_name: str,
        correct: bool,
        kind: str = "practice",
        detail: str = "",
    ) -> float:
        with self._write() as connection:
            current = self._check_revision(connection, student_id, None)
            revision = self._next_revision(connection, student_id, current)
            source = "diagnose" if kind == "diagnose" else "practice"
            mastery = self._apply_evidence(
                connection, student_id, node_id, node_name, correct, source, revision
            )
            self._event(
                connection,
                student_id=student_id,
                node_id=node_id,
                kind=kind,
                correct=correct,
                detail=detail,
                revision=revision,
            )
            return mastery

    def seed(
        self,
        student_id: str,
        node_id: str,
        node_name: str,
        value: float,
        detail: str = "diagnose_propagate",
    ) -> float:
        value = max(0.0, min(1.0, float(value)))
        with self._write() as connection:
            current = self._check_revision(connection, student_id, None)
            revision = self._next_revision(connection, student_id, current)
            row = connection.execute(
                "SELECT mastery FROM mastery WHERE student_id=? AND node_id=?",
                (student_id, node_id),
            ).fetchone()
            mastery = max(float(row["mastery"]), value) if row else value
            now = time.time()
            connection.execute(
                "INSERT INTO mastery(student_id,node_id,node_name,mastery,attempts,correct,updated_at,"
                "evidence_source,revision) VALUES(?,?,?,?,0,0,?,'diagnose',?) "
                "ON CONFLICT(student_id,node_id) DO UPDATE SET "
                "node_name=COALESCE(NULLIF(excluded.node_name,''),mastery.node_name),"
                "mastery=MAX(mastery.mastery,excluded.mastery),updated_at=excluded.updated_at,"
                "evidence_source='diagnose',revision=excluded.revision",
                (student_id, node_id, node_name, mastery, now, revision),
            )
            self._event(
                connection,
                student_id=student_id,
                node_id=node_id,
                kind="diagnose",
                detail=detail,
                revision=revision,
            )
            return mastery

    def note(self, student_id: str, detail: str, node_id: str | None = None) -> None:
        with self._write() as connection:
            current = self._check_revision(connection, student_id, None)
            revision = self._next_revision(connection, student_id, current)
            self._event(
                connection,
                student_id=student_id,
                node_id=node_id,
                kind="note",
                detail=detail,
                revision=revision,
            )

    def profile(self, student_id: str) -> dict:
        with self._read() as connection:
            revision = self._revision(connection, student_id)
            rows = connection.execute(
                "SELECT student_id,node_id,node_name,mastery,attempts,correct,updated_at,"
                "evidence_source,manual_override,revision FROM mastery WHERE student_id=? "
                "ORDER BY mastery DESC,node_id",
                (student_id,),
            ).fetchall()
            nodes = [self._mastery_dict(row) for row in rows]
        mastered = [
            node["node_id"]
            for node in nodes
            if node["mastery_state"] in {"assessed_mastery", "self_reported_mastery"}
        ]
        return {
            "student_id": student_id,
            "revision": revision,
            "total_tracked": len(nodes),
            "mastered": mastered,
            "weak": [node for node in nodes if node["node_id"] not in mastered],
            "nodes": nodes,
        }

    def mastered_ids(self, student_id: str) -> list[str]:
        return self.profile(student_id)["mastered"]

    def prunable_ids(self, student_id: str) -> list[str]:
        with self._read() as connection:
            return [
                row["node_id"]
                for row in connection.execute(
                    "SELECT node_id FROM mastery WHERE student_id=? "
                    "AND (mastery>=? OR manual_override='mastered') ORDER BY node_id",
                    (student_id, config.PRUNE_THRESHOLD),
                ).fetchall()
            ]

    def history(self, student_id: str, node_id: str | None = None, limit: int = 20) -> list[dict]:
        query = (
            "SELECT node_id,kind,correct,detail,question_id,target_id,path_node_id,source_page,"
            "revision,created_at FROM events WHERE student_id=?"
        )
        arguments: list[Any] = [student_id]
        if node_id:
            query += " AND node_id=?"
            arguments.append(node_id)
        query += " ORDER BY created_at DESC,id DESC LIMIT ?"
        arguments.append(limit)
        with self._read() as connection:
            return [dict(row) for row in connection.execute(query, arguments).fetchall()]

    def set_manual_override(
        self,
        student_id: str,
        node_id: str,
        manual_override: str | None,
        expected_revision: int | None,
        idempotency_key: str,
        node_name: str = "",
    ) -> dict:
        if manual_override not in {None, "mastered", "learning"}:
            raise InvalidLearningContext("manual_override 必须为 mastered、learning 或 null")
        operation = f"knowledge:{node_id}"
        with self._write() as connection:
            cached = self._idempotent_result(
                connection, student_id, idempotency_key, operation
            )
            if cached:
                return cached
            current = self._check_revision(connection, student_id, expected_revision)
            revision = self._next_revision(connection, student_id, current)
            now = time.time()
            connection.execute(
                "INSERT INTO mastery(student_id,node_id,node_name,mastery,attempts,correct,updated_at,"
                "evidence_source,manual_override,revision) VALUES(?,?,?,0,0,0,?,'manual',?,?) "
                "ON CONFLICT(student_id,node_id) DO UPDATE SET "
                "node_name=COALESCE(NULLIF(excluded.node_name,''),mastery.node_name),"
                "manual_override=excluded.manual_override,updated_at=excluded.updated_at,"
                "revision=excluded.revision",
                (student_id, node_id, node_name, now, manual_override, revision),
            )
            self._event(
                connection,
                student_id=student_id,
                node_id=node_id,
                kind="manual",
                detail=f"manual_override={manual_override or 'none'}",
                idempotency_key=idempotency_key,
                source_page="graph",
                revision=revision,
            )
            row = connection.execute(
                "SELECT student_id,node_id,node_name,mastery,attempts,correct,updated_at,"
                "evidence_source,manual_override,revision FROM mastery "
                "WHERE student_id=? AND node_id=?",
                (student_id, node_id),
            ).fetchone()
            result = {"revision": revision, "knowledge": self._mastery_dict(row)}
            self._save_idempotent_result(
                connection, student_id, idempotency_key, operation, result
            )
            return result

    def set_plan_step(
        self,
        student_id: str,
        target_id: str,
        node_id: str,
        status: str,
        expected_revision: int | None,
        idempotency_key: str,
    ) -> dict:
        if status not in {"in_progress", "completed"}:
            raise InvalidLearningContext("status 必须为 in_progress 或 completed")
        operation = f"plan-step:{target_id}:{node_id}"
        with self._write() as connection:
            cached = self._idempotent_result(
                connection, student_id, idempotency_key, operation
            )
            if cached:
                return cached
            current = self._check_revision(connection, student_id, expected_revision)
            issued = connection.execute(
                "SELECT 1 FROM issued_plan_steps WHERE student_id=? AND target_id=? AND node_id=?",
                (student_id, target_id, node_id),
            ).fetchone()
            existing_progress = connection.execute(
                "SELECT 1 FROM plan_progress WHERE student_id=? AND target_id=? AND node_id=?",
                (student_id, target_id, node_id),
            ).fetchone()
            if issued is None and not (status == "in_progress" and existing_progress):
                raise InvalidLearningContext("该步骤不属于最近签发的学习路径")
            revision = self._next_revision(connection, student_id, current)
            now = time.time()
            completed_at = now if status == "completed" else None
            connection.execute(
                "INSERT INTO plan_progress(student_id,target_id,node_id,status,completed_at,updated_at,revision) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(student_id,target_id,node_id) DO UPDATE SET "
                "status=excluded.status,completed_at=excluded.completed_at,"
                "updated_at=excluded.updated_at,revision=excluded.revision",
                (student_id, target_id, node_id, status, completed_at, now, revision),
            )
            self._event(
                connection,
                student_id=student_id,
                node_id=node_id,
                kind="plan_progress",
                detail=status,
                target_id=target_id,
                path_node_id=node_id,
                idempotency_key=idempotency_key,
                source_page="graph",
                revision=revision,
            )
            result = {
                "revision": revision,
                "target_id": target_id,
                "node_id": node_id,
                "status": status,
                "completed_at": completed_at,
            }
            self._save_idempotent_result(
                connection, student_id, idempotency_key, operation, result
            )
            return result

    def _question_knowledge(self, question_id: str) -> list[dict]:
        if self.graph is None:
            raise GraphUnavailable("图谱服务未配置")
        try:
            data = _unwrap_graph(self.graph.knowledge_of_question(question_id))
        except Exception as exc:
            raise GraphUnavailable("无法读取题目知识点关系") from exc
        if not isinstance(data, list):
            return []
        rows = [row for row in data if isinstance(row, dict)]
        if any(row.get("weight") is not None for row in rows):
            return sorted(
                rows,
                key=lambda row: (
                    -float(row.get("weight", 0) or 0),
                    str(row.get("id") or row.get("node_id") or ""),
                ),
            )
        return rows

    def _attribution(
        self,
        connection: sqlite3.Connection,
        student_id: str,
        question_id: str,
        target_id: str | None,
        path_node_id: str | None,
    ) -> list[dict]:
        related: list[dict] = []
        if target_id or path_node_id:
            if not target_id or not path_node_id:
                raise InvalidLearningContext("target_id 与 path_node_id 必须同时提交")
            issued = connection.execute(
                "SELECT question_ids FROM issued_plan_steps "
                "WHERE student_id=? AND target_id=? AND node_id=?",
                (student_id, target_id, path_node_id),
            ).fetchone()
            if issued is None:
                raise InvalidLearningContext("作答步骤不属于最近签发的学习路径")
            question_ids = json.loads(issued["question_ids"] or "[]")
            if question_id not in question_ids:
                raise InvalidLearningContext("该题目不属于指定的学习路径步骤")
            try:
                related = self._question_knowledge(question_id)
            except GraphUnavailable:
                related = []
            primary_name = next(
                (
                    str(row.get("name") or "")
                    for row in related
                    if str(row.get("id") or row.get("node_id") or "") == path_node_id
                ),
                "",
            )
            attribution = [
                {"node_id": path_node_id, "name": primary_name, "role": "primary", "weight": 1.0}
            ]
            for row in related:
                node_id = str(row.get("id") or row.get("node_id") or "")
                if node_id and node_id != path_node_id:
                    attribution.append(
                        {
                            "node_id": node_id,
                            "name": str(row.get("name") or ""),
                            "role": "supporting",
                            "weight": float(row.get("weight", 0.5) or 0.5),
                        }
                    )
            return attribution

        related = self._question_knowledge(question_id)
        if not related:
            raise InvalidLearningContext("题目没有可用于归因的知识点")
        attribution = []
        seen: set[str] = set()
        for row in related:
            node_id = str(row.get("id") or row.get("node_id") or "")
            if not node_id or node_id in seen:
                continue
            seen.add(node_id)
            attribution.append(
                {
                    "node_id": node_id,
                    "name": str(row.get("name") or ""),
                    "role": "primary" if not attribution else "supporting",
                    "weight": 1.0 if not attribution else float(row.get("weight", 0.5) or 0.5),
                }
            )
        return attribution

    def record_attempt(
        self,
        student_id: str,
        question_id: str,
        correct: bool,
        source_page: str,
        expected_revision: int | None,
        idempotency_key: str,
        target_id: str | None = None,
        path_node_id: str | None = None,
    ) -> dict:
        operation = "attempt"
        with self._write() as connection:
            cached = self._idempotent_result(
                connection, student_id, idempotency_key, operation
            )
            if cached:
                return cached
            current = self._check_revision(connection, student_id, expected_revision)
            attribution = self._attribution(
                connection, student_id, question_id, target_id, path_node_id
            )
            revision = self._next_revision(connection, student_id, current)
            attempt_id = str(uuid.uuid4())
            now = time.time()
            connection.execute(
                "INSERT INTO question_attempts(attempt_id,student_id,question_id,target_id,path_node_id,"
                "correct,source_page,attempted_at,idempotency_key,revision) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    attempt_id,
                    student_id,
                    question_id,
                    target_id,
                    path_node_id,
                    int(correct),
                    source_page,
                    now,
                    idempotency_key,
                    revision,
                ),
            )
            for item in attribution:
                connection.execute(
                    "INSERT INTO attempt_knowledge(attempt_id,node_id,role,weight) VALUES(?,?,?,?)",
                    (attempt_id, item["node_id"], item["role"], item["weight"]),
                )
            primary = next(item for item in attribution if item["role"] == "primary")
            mastery = self._apply_evidence(
                connection,
                student_id,
                primary["node_id"],
                primary["name"],
                bool(correct),
                "practice",
                revision,
            )
            existing_mistake = connection.execute(
                "SELECT * FROM mistake_items WHERE student_id=? AND question_id=?",
                (student_id, question_id),
            ).fetchone()
            if not correct:
                wrong_count = int(existing_mistake["wrong_count"]) + 1 if existing_mistake else 1
                correct_after = (
                    int(existing_mistake["correct_after_wrong_count"]) if existing_mistake else 0
                )
                connection.execute(
                    "INSERT INTO mistake_items(student_id,question_id,status,resolution,wrong_count,"
                    "correct_after_wrong_count,last_wrong_at,resolved_at,updated_at,revision) "
                    "VALUES(?,?,'open',NULL,?,?,?,NULL,?,?) "
                    "ON CONFLICT(student_id,question_id) DO UPDATE SET status='open',resolution=NULL,"
                    "wrong_count=excluded.wrong_count,last_wrong_at=excluded.last_wrong_at,"
                    "resolved_at=NULL,updated_at=excluded.updated_at,revision=excluded.revision",
                    (student_id, question_id, wrong_count, correct_after, now, now, revision),
                )
            elif existing_mistake and existing_mistake["status"] == "open":
                connection.execute(
                    "UPDATE mistake_items SET status='resolved',resolution='correct_retry',"
                    "correct_after_wrong_count=correct_after_wrong_count+1,resolved_at=?,updated_at=?,"
                    "revision=? WHERE student_id=? AND question_id=?",
                    (now, now, revision, student_id, question_id),
                )
            self._event(
                connection,
                student_id=student_id,
                node_id=primary["node_id"],
                kind="practice",
                correct=bool(correct),
                detail=f"question={question_id}",
                question_id=question_id,
                target_id=target_id,
                path_node_id=path_node_id,
                idempotency_key=idempotency_key,
                source_page=source_page,
                revision=revision,
            )
            mistake = connection.execute(
                "SELECT * FROM mistake_items WHERE student_id=? AND question_id=?",
                (student_id, question_id),
            ).fetchone()
            result = {
                "revision": revision,
                "attempt_id": attempt_id,
                "question_id": question_id,
                "correct": bool(correct),
                "attribution": attribution,
                "primary_mastery": mastery,
                "mistake": dict(mistake) if mistake else None,
            }
            self._save_idempotent_result(
                connection, student_id, idempotency_key, operation, result
            )
            return result

    def resolve_mistake(
        self,
        student_id: str,
        question_id: str,
        resolution: str,
        expected_revision: int | None,
        idempotency_key: str,
    ) -> dict:
        if resolution != "manual_review":
            raise InvalidLearningContext("手动解决方式必须为 manual_review")
        operation = f"mistake:{question_id}"
        with self._write() as connection:
            cached = self._idempotent_result(
                connection, student_id, idempotency_key, operation
            )
            if cached:
                return cached
            current = self._check_revision(connection, student_id, expected_revision)
            existing = connection.execute(
                "SELECT * FROM mistake_items WHERE student_id=? AND question_id=?",
                (student_id, question_id),
            ).fetchone()
            if existing is None:
                raise InvalidLearningContext("错题不存在")
            revision = self._next_revision(connection, student_id, current)
            now = time.time()
            connection.execute(
                "UPDATE mistake_items SET status='resolved',resolution=?,resolved_at=?,updated_at=?,"
                "revision=? WHERE student_id=? AND question_id=?",
                (resolution, now, now, revision, student_id, question_id),
            )
            self._event(
                connection,
                student_id=student_id,
                kind="mistake_resolved",
                detail=resolution,
                question_id=question_id,
                idempotency_key=idempotency_key,
                source_page="graph",
                revision=revision,
            )
            result = {
                "revision": revision,
                "question_id": question_id,
                "status": "resolved",
                "resolution": resolution,
                "resolved_at": now,
            }
            self._save_idempotent_result(
                connection, student_id, idempotency_key, operation, result
            )
            return result

    @staticmethod
    def _mistake_rows(
        connection: sqlite3.Connection, student_id: str, status: str | None = None
    ) -> list[dict]:
        query = (
            "SELECT m.*,qa.target_id,qa.path_node_id,ak.node_id AS primary_node_id,"
            "mm.node_name AS primary_node_name FROM mistake_items m "
            "LEFT JOIN question_attempts qa ON qa.attempt_id=(SELECT q2.attempt_id "
            "FROM question_attempts q2 WHERE q2.student_id=m.student_id "
            "AND q2.question_id=m.question_id ORDER BY q2.attempted_at DESC LIMIT 1) "
            "LEFT JOIN attempt_knowledge ak ON ak.attempt_id=qa.attempt_id AND ak.role='primary' "
            "LEFT JOIN mastery mm ON mm.student_id=m.student_id AND mm.node_id=ak.node_id "
            "WHERE m.student_id=?"
        )
        arguments: list[Any] = [student_id]
        if status:
            query += " AND m.status=?"
            arguments.append(status)
        query += " ORDER BY m.updated_at DESC,m.question_id"
        return [dict(row) for row in connection.execute(query, arguments).fetchall()]

    def mistakes(
        self, student_id: str, status: str | None = None, target_id: str | None = None
    ) -> dict:
        if status not in {None, "open", "resolved"}:
            raise InvalidLearningContext("status 必须为 open 或 resolved")
        with self._read() as connection:
            revision = self._revision(connection, student_id)
            items = self._mistake_rows(connection, student_id, status)
            target_nodes: set[str] = set()
            if target_id:
                target_nodes = {
                    row["node_id"]
                    for row in connection.execute(
                        "SELECT node_id FROM issued_plan_steps WHERE student_id=? AND target_id=?",
                        (student_id, target_id),
                    ).fetchall()
                }
            for item in items:
                item["unresolved"] = item["status"] == "open"
                item["target_related"] = bool(
                    target_id
                    and (
                        item.get("target_id") == target_id
                        or item.get("primary_node_id") in target_nodes
                    )
                )
        return {"revision": revision, "items": items}

    @staticmethod
    def _mistake_summary(items: list[dict]) -> dict:
        grouped: dict[str, dict] = {}
        for item in items:
            node_id = item.get("primary_node_id") or "unattributed"
            group = grouped.setdefault(
                node_id,
                {
                    "node_id": node_id,
                    "node_name": item.get("primary_node_name") or node_id,
                    "open_count": 0,
                    "wrong_count": 0,
                },
            )
            group["wrong_count"] += int(item.get("wrong_count") or 0)
            if item.get("status") == "open":
                group["open_count"] += 1
        return {
            "total": len(items),
            "open": sum(item.get("status") == "open" for item in items),
            "resolved": sum(item.get("status") == "resolved" for item in items),
            "wrong_attempts": sum(int(item.get("wrong_count") or 0) for item in items),
            "by_knowledge": sorted(grouped.values(), key=lambda row: (-row["open_count"], row["node_id"])),
        }

    def state(self, student_id: str) -> dict:
        with self._read() as connection:
            revision = self._revision(connection, student_id)
            mastery_rows = connection.execute(
                "SELECT student_id,node_id,node_name,mastery,attempts,correct,updated_at,"
                "evidence_source,manual_override,revision FROM mastery WHERE student_id=? "
                "ORDER BY mastery DESC,node_id",
                (student_id,),
            ).fetchall()
            mastery_nodes = [self._mastery_dict(row) for row in mastery_rows]
            progress = [
                dict(row)
                for row in connection.execute(
                    "SELECT target_id,node_id,status,completed_at,updated_at,revision "
                    "FROM plan_progress WHERE student_id=? ORDER BY target_id,node_id",
                    (student_id,),
                ).fetchall()
            ]
            mistakes = self._mistake_rows(connection, student_id)
            events = [
                dict(row)
                for row in connection.execute(
                    "SELECT node_id,kind,correct,detail,question_id,target_id,path_node_id,"
                    "source_page,revision,created_at FROM events WHERE student_id=? "
                    "ORDER BY created_at DESC,id DESC LIMIT 50",
                    (student_id,),
                ).fetchall()
            ]
            meta = connection.execute(
                "SELECT local_v1_imported,local_v1_hash FROM learner_state_meta WHERE student_id=?",
                (student_id,),
            ).fetchone()
        mastered = [
            node["node_id"]
            for node in mastery_nodes
            if node["mastery_state"] in {"assessed_mastery", "self_reported_mastery"}
        ]
        profile = {
            "student_id": student_id,
            "revision": revision,
            "total_tracked": len(mastery_nodes),
            "mastered": mastered,
            "weak": [node for node in mastery_nodes if node["node_id"] not in mastered],
            "nodes": mastery_nodes,
        }
        return {
            "student_id": student_id,
            "revision": revision,
            "profile": profile,
            "mastery_nodes": mastery_nodes,
            "plan_progress": progress,
            "mistake_summary": self._mistake_summary(mistakes),
            "open_mistakes": [item for item in mistakes if item["status"] == "open"],
            "recent_events": events,
            "local_v1_imported": bool(meta["local_v1_imported"]),
            "local_v1_hash": meta["local_v1_hash"],
        }

    def dashboard(self, student_id: str) -> dict:
        state = self.state(student_id)
        nodes_by_id = {node["node_id"]: node for node in state["mastery_nodes"]}
        knowledge_points: list[dict] = []
        if self.graph is not None:
            try:
                data = _unwrap_graph(self.graph.list_knowledge_points(limit=2000))
                if isinstance(data, list):
                    knowledge_points = [row for row in data if isinstance(row, dict)]
            except Exception as exc:
                raise GraphUnavailable("无法读取知识点目录") from exc
        if not knowledge_points:
            knowledge_points = [
                {"id": node["node_id"], "name": node.get("node_name") or node["node_id"]}
                for node in state["mastery_nodes"]
            ]
        summary = {"total": len(knowledge_points), "mastered": 0, "in_progress": 0, "not_started": 0}
        chapters: dict[str, dict] = {}
        rows = []
        for item in knowledge_points:
            node_id = str(item.get("id") or item.get("node_id") or "")
            if not node_id:
                continue
            learner = nodes_by_id.get(node_id)
            if learner and learner["mastery_state"] in {"assessed_mastery", "self_reported_mastery"}:
                status = "mastered"
            elif learner:
                status = "in_progress"
            else:
                status = "not_started"
            summary[status] += 1
            mastery_percent = round(float(learner["mastery"]) * 100) if learner else 0
            row = {
                "id": node_id,
                "name": item.get("name") or node_id,
                "chapter_id": item.get("chapter_id"),
                "status": status,
                "mastery": mastery_percent,
                "mastery_state": learner.get("mastery_state") if learner else "untested",
                "updated_at": learner.get("updated_at") if learner else None,
            }
            rows.append(row)
            chapter_id = str(item.get("chapter_id") or "unassigned")
            chapter = chapters.setdefault(
                chapter_id,
                {"id": chapter_id, "name": f"第 {chapter_id} 章" if chapter_id != "unassigned" else "未分章", "total": 0, "mastered": 0, "in_progress": 0, "not_started": 0, "mastery_total": 0},
            )
            chapter["total"] += 1
            chapter[status] += 1
            chapter["mastery_total"] += mastery_percent
        summary["mastery_percent"] = (
            round(sum(row["mastery"] for row in rows) / len(rows)) if rows else 0
        )
        chapter_progress = []
        for chapter in chapters.values():
            mastery_total = chapter.pop("mastery_total")
            chapter["mastery_percent"] = round(mastery_total / chapter["total"])
            chapter_progress.append(chapter)
        recent = sorted(
            (row for row in rows if row["updated_at"]),
            key=lambda row: float(row["updated_at"]),
            reverse=True,
        )[:6]
        completed_targets = {
            str(item["target_id"])
            for item in state["plan_progress"]
            if item["status"] == "completed" and item["node_id"] == item["target_id"]
        }
        recommendation = next(
            (
                row
                for row in recent
                if row["status"] == "in_progress" and row["id"] not in completed_targets
            ),
            None,
        )
        if recommendation is None:
            recommendation = next(
                (
                    row
                    for row in rows
                    if row["status"] != "mastered" and row["id"] not in completed_targets
                ),
                None,
            )
        if recommendation:
            recommendation = {
                **recommendation,
                "reason": "继续最近的学习内容" if recommendation["status"] == "in_progress" else "从尚未学习的知识点开始",
            }
        return {
            "student_id": student_id,
            "revision": state["revision"],
            "summary": summary,
            "chapter_progress": sorted(chapter_progress, key=lambda row: row["id"]),
            "mistake_summary": {
                "total": state["mistake_summary"]["total"],
                "unresolved": state["mistake_summary"]["open"],
                "resolved": state["mistake_summary"]["resolved"],
                "wrong_attempts": state["mistake_summary"]["wrong_attempts"],
            },
            "recent": recent,
            "recommendation": recommendation,
            "mastery_nodes": state["mastery_nodes"],
        }

    def _graph_plan(self, **payload: Any) -> dict:
        if self.graph is None:
            raise GraphUnavailable("图谱服务未配置")
        try:
            data = _unwrap_graph(self.graph.generate_plan(**payload))
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code == 404:
                raise LearningTargetNotFound(f"未找到知识点: {payload.get('target')}") from exc
            raise GraphUnavailable("图谱路径服务不可用") from exc
        if not isinstance(data, dict) or not isinstance(data.get("target"), dict):
            raise LearningTargetNotFound(f"未找到知识点: {payload.get('target')}")
        return data

    def generate_plan(
        self,
        student_id: str,
        target: str,
        difficulty_preference: str = "balanced",
        max_depth: int = 6,
        questions_per_step: int = 3,
        expected_revision: int | None = None,
    ) -> dict:
        with self._read() as connection:
            revision = self._check_revision(connection, student_id, expected_revision)
            mastery_rows = connection.execute(
                "SELECT node_id,mastery,attempts,manual_override FROM mastery WHERE student_id=? "
                "AND (mastery>=? OR manual_override='mastered')",
                (student_id, config.PRUNE_THRESHOLD),
            ).fetchall()
            prunable = [row["node_id"] for row in mastery_rows]
            reason_by_id = {}
            for row in mastery_rows:
                if row["manual_override"] == "mastered":
                    reason = "manual_override"
                elif int(row["attempts"]) > 0 and float(row["mastery"]) >= config.MASTERY_THRESHOLD:
                    reason = "assessed_mastery"
                else:
                    reason = "soft_confidence"
                reason_by_id[row["node_id"]] = reason

        first = self._graph_plan(
            target=target,
            mastered=prunable,
            completed=[],
            difficulty_preference=difficulty_preference,
            questions_per_step=questions_per_step,
            max_depth=max_depth,
        )
        target_id = str(first["target"].get("id") or "")
        if not target_id:
            raise LearningTargetNotFound(f"未找到知识点: {target}")
        # Soft confidence is enough to prune a prerequisite, but never enough
        # to skip the learner's explicit target. The first graph call resolves
        # names to a canonical target ID; rerun only when that target was
        # optimistically pruned by sub-threshold evidence.
        plan_prunable = prunable
        if target_id in prunable and reason_by_id.get(target_id) == "soft_confidence":
            plan_prunable = [node_id for node_id in prunable if node_id != target_id]
            first = self._graph_plan(
                target=target_id,
                mastered=plan_prunable,
                completed=[],
                difficulty_preference=difficulty_preference,
                questions_per_step=questions_per_step,
                max_depth=max_depth,
            )
        with self._read() as connection:
            current = self._check_revision(connection, student_id, revision)
            completed = [
                row["node_id"]
                for row in connection.execute(
                    "SELECT node_id FROM plan_progress WHERE student_id=? AND target_id=? "
                    "AND status='completed'",
                    (student_id, target_id),
                ).fetchall()
            ]
        plan = first
        if completed:
            plan = self._graph_plan(
                target=target_id,
                mastered=plan_prunable,
                completed=completed,
                difficulty_preference=difficulty_preference,
                questions_per_step=questions_per_step,
                max_depth=max_depth,
            )
        with self._write() as connection:
            self._check_revision(connection, student_id, current)
            connection.execute(
                "DELETE FROM issued_plan_steps WHERE student_id=? AND target_id=?",
                (student_id, target_id),
            )
            for step in plan.get("steps") or []:
                question_ids = [
                    str(question.get("id"))
                    for question in (step.get("questions") or [])
                    if question.get("id")
                ]
                connection.execute(
                    "INSERT INTO issued_plan_steps(student_id,target_id,node_id,question_ids,issued_at,"
                    "state_revision) VALUES(?,?,?,?,?,?)",
                    (student_id, target_id, step.get("id"), _json(question_ids), time.time(), current),
                )
            mastery_nodes = {
                row["node_id"]: self._mastery_dict(row)
                for row in connection.execute(
                    "SELECT student_id,node_id,node_name,mastery,attempts,correct,updated_at,"
                    "evidence_source,manual_override,revision FROM mastery WHERE student_id=?",
                    (student_id,),
                ).fetchall()
            }
            progress = {
                row["node_id"]: dict(row)
                for row in connection.execute(
                    "SELECT node_id,status,completed_at,updated_at FROM plan_progress "
                    "WHERE student_id=? AND target_id=?",
                    (student_id, target_id),
                ).fetchall()
            }
            mistakes = [
                item
                for item in self._mistake_rows(connection, student_id, "open")
                if item.get("primary_node_id")
            ]

        step_ids = {str(step.get("id")) for step in plan.get("steps") or []}
        related_ids = step_ids | {
            str(item.get("id")) for item in plan.get("mastered_skipped") or []
        } | {str(item.get("id")) for item in plan.get("completed_skipped") or []} | {target_id}
        reviews_by_node: dict[str, list[dict]] = {}
        review_before = []
        for mistake in mistakes:
            node_id = mistake["primary_node_id"]
            task = {
                "question_id": mistake["question_id"],
                "node_id": node_id,
                "wrong_count": mistake["wrong_count"],
                "last_wrong_at": mistake["last_wrong_at"],
                "status": mistake["status"],
            }
            if node_id in step_ids:
                reviews_by_node.setdefault(node_id, []).append(task)
            elif node_id in related_ids:
                review_before.append(task)

        enriched_steps = []
        for step in plan.get("steps") or []:
            node_id = str(step.get("id"))
            mastery = mastery_nodes.get(node_id)
            reviews = reviews_by_node.get(node_id, [])
            enriched_steps.append(
                {
                    **step,
                    "node_id": node_id,
                    "mastery_state": mastery["mastery_state"] if mastery else "untested",
                    "mastery": mastery["mastery"] if mastery else 0.0,
                    "evidence_source": mastery["evidence_source"] if mastery else None,
                    "manual_override": mastery["manual_override"] if mastery else None,
                    "progress_status": progress.get(node_id, {}).get("status", "not_started"),
                    "mistake_count": len(reviews),
                    "review_tasks": reviews,
                }
            )
        skipped = [
            {**item, "reason": reason_by_id.get(str(item.get("id")), "soft_confidence")}
            for item in plan.get("mastered_skipped") or []
        ] + [
            {**item, "reason": "completed_for_target"}
            for item in plan.get("completed_skipped") or []
        ]
        target_mastery = mastery_nodes.get(target_id)
        return {
            **plan,
            "revision": current,
            "target_id": target_id,
            "steps": enriched_steps,
            "skipped": skipped,
            "review_before_plan": review_before,
            "target_mastery_state": (
                target_mastery["mastery_state"] if target_mastery else "untested"
            ),
            "target_manual_override": (
                target_mastery["manual_override"] if target_mastery else None
            ),
        }

    def import_local_v1(
        self,
        student_id: str,
        payload: dict,
        expected_revision: int | None = None,
        preview: bool = False,
    ) -> dict:
        if not isinstance(payload, dict) or int(payload.get("version", 0)) != 1:
            raise InvalidLearningContext("仅支持 version=1 的本地学习状态")
        for field in ("mastered", "progress", "mistakes", "plan_done"):
            value = payload.get(field, {})
            if not isinstance(value, dict):
                raise InvalidLearningContext(f"字段 {field} 格式无效")
        content_hash = hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()
        if preview:
            with self._read() as connection:
                row = connection.execute(
                    "SELECT revision FROM learner_state_meta WHERE student_id=?",
                    (student_id,),
                ).fetchone()
                current = int(row["revision"]) if row else 0
                if expected_revision is not None and expected_revision != current:
                    raise RevisionConflict(current)
            return {
                "content_hash": content_hash,
                "preview": True,
                "revision": current,
                "imported": {"mastered": 0, "progress": 0, "plan_done": 0, "mistakes": 0},
                "skipped": {"mastered": 0, "progress": 0, "plan_done": 0, "mistakes": 0},
                "conflicts": 0,
                "summary": {
                    field: len(payload.get(field, {}))
                    for field in ("mastered", "progress", "plan_done", "mistakes")
                },
            }
        with self._write() as connection:
            cached = connection.execute(
                "SELECT report_json FROM local_imports WHERE student_id=? AND content_hash=?",
                (student_id, content_hash),
            ).fetchone()
            if cached:
                report = json.loads(cached["report_json"])
                report["idempotent"] = True
                return report
            current = self._check_revision(connection, student_id, expected_revision)
            report: dict[str, Any] = {
                "content_hash": content_hash,
                "preview": preview,
                "imported": {"mastered": 0, "progress": 0, "plan_done": 0, "mistakes": 0},
                "skipped": {"mastered": 0, "progress": 0, "plan_done": 0, "mistakes": 0},
                "conflicts": 0,
            }
            revision = self._next_revision(connection, student_id, current)
            now = time.time()
            mastered_ids = set(payload.get("mastered", {}))
            for node_id, value in payload.get("progress", {}).items():
                if isinstance(value, dict) and value.get("status") == "mastered":
                    mastered_ids.add(node_id)
            for node_id in sorted(mastered_ids):
                existing = connection.execute(
                    "SELECT attempts,manual_override FROM mastery WHERE student_id=? AND node_id=?",
                    (student_id, node_id),
                ).fetchone()
                if existing and existing["manual_override"] == "mastered":
                    report["skipped"]["mastered"] += 1
                    continue
                if existing and int(existing["attempts"]) > 0:
                    report["conflicts"] += 1
                connection.execute(
                    "INSERT INTO mastery(student_id,node_id,node_name,mastery,attempts,correct,updated_at,"
                    "evidence_source,manual_override,revision) VALUES(?,?,NULL,0,0,0,?,'migration','mastered',?) "
                    "ON CONFLICT(student_id,node_id) DO UPDATE SET manual_override='mastered',"
                    "updated_at=excluded.updated_at,revision=excluded.revision",
                    (student_id, node_id, now, revision),
                )
                report["imported"]["mastered"] += 1
            for node_id, value in payload.get("progress", {}).items():
                if not isinstance(value, dict):
                    report["skipped"]["progress"] += 1
                    continue
                updated_at = _timestamp(value.get("updated_at"), now)
                existing = connection.execute(
                    "SELECT updated_at FROM node_activity WHERE student_id=? AND node_id=?",
                    (student_id, node_id),
                ).fetchone()
                if existing and float(existing["updated_at"]) >= updated_at:
                    report["skipped"]["progress"] += 1
                    continue
                connection.execute(
                    "INSERT INTO node_activity(student_id,node_id,status,mastery_hint,last_seen_at,"
                    "updated_at,revision) VALUES(?,?,?,?,?,?,?) "
                    "ON CONFLICT(student_id,node_id) DO UPDATE SET status=excluded.status,"
                    "mastery_hint=excluded.mastery_hint,last_seen_at=excluded.last_seen_at,"
                    "updated_at=excluded.updated_at,revision=excluded.revision",
                    (
                        student_id,
                        node_id,
                        value.get("status") or "not_started",
                        max(0.0, min(1.0, float(value.get("mastery", 0) or 0) / 100)),
                        _timestamp(value.get("last_seen_at"), updated_at),
                        updated_at,
                        revision,
                    ),
                )
                report["imported"]["progress"] += 1
            for target_id, steps in payload.get("plan_done", {}).items():
                if not isinstance(steps, dict):
                    report["skipped"]["plan_done"] += 1
                    continue
                for node_id, completed_value in steps.items():
                    completed_at = _timestamp(completed_value, now)
                    existing = connection.execute(
                        "SELECT completed_at FROM plan_progress WHERE student_id=? AND target_id=? AND node_id=?",
                        (student_id, target_id, node_id),
                    ).fetchone()
                    if existing and float(existing["completed_at"] or 0) >= completed_at:
                        report["skipped"]["plan_done"] += 1
                        continue
                    connection.execute(
                        "INSERT INTO plan_progress(student_id,target_id,node_id,status,completed_at,"
                        "updated_at,revision) VALUES(?,?,?,'completed',?,?,?) "
                        "ON CONFLICT(student_id,target_id,node_id) DO UPDATE SET status='completed',"
                        "completed_at=excluded.completed_at,updated_at=excluded.updated_at,"
                        "revision=excluded.revision",
                        (student_id, target_id, node_id, completed_at, completed_at, revision),
                    )
                    report["imported"]["plan_done"] += 1
            for question_id, value in payload.get("mistakes", {}).items():
                if not isinstance(value, dict):
                    report["skipped"]["mistakes"] += 1
                    continue
                local_wrong = max(0, int(value.get("wrong_count", 0) or 0))
                if local_wrong == 0:
                    report["skipped"]["mistakes"] += 1
                    continue
                existing = connection.execute(
                    "SELECT wrong_count,status FROM mistake_items WHERE student_id=? AND question_id=?",
                    (student_id, question_id),
                ).fetchone()
                wrong_count = max(local_wrong, int(existing["wrong_count"]) if existing else 0)
                unresolved = value.get("unresolved") is not False
                status = "open" if unresolved else "resolved"
                updated_at = _timestamp(value.get("last_attempt_at"), now)
                connection.execute(
                    "INSERT INTO mistake_items(student_id,question_id,status,resolution,wrong_count,"
                    "correct_after_wrong_count,last_wrong_at,resolved_at,updated_at,revision) "
                    "VALUES(?,?,?,?,?,0,?,?,?,?) ON CONFLICT(student_id,question_id) DO UPDATE SET "
                    "status=mistake_items.status,resolution=mistake_items.resolution,"
                    "wrong_count=MAX(mistake_items.wrong_count,excluded.wrong_count),"
                    "last_wrong_at=MAX(mistake_items.last_wrong_at,excluded.last_wrong_at),"
                    "updated_at=MAX(mistake_items.updated_at,excluded.updated_at),revision=excluded.revision",
                    (
                        student_id,
                        question_id,
                        status,
                        None if unresolved else "manual_review",
                        wrong_count,
                        updated_at,
                        None if unresolved else updated_at,
                        updated_at,
                        revision,
                    ),
                )
                knowledge_ids = value.get("knowledge_ids") or []
                if knowledge_ids:
                    attempt_id = f"migration:{content_hash[:12]}:{question_id}"
                    key = f"migration:{content_hash}:{question_id}"
                    connection.execute(
                        "INSERT OR IGNORE INTO question_attempts(attempt_id,student_id,question_id,"
                        "correct,source_page,attempted_at,idempotency_key,revision) VALUES(?,?,?,0,'migration',?,?,?)",
                        (attempt_id, student_id, question_id, updated_at, key, revision),
                    )
                    for index, node_id in enumerate(dict.fromkeys(knowledge_ids)):
                        connection.execute(
                            "INSERT OR IGNORE INTO attempt_knowledge(attempt_id,node_id,role,weight) "
                            "VALUES(?,?,?,?)",
                            (attempt_id, node_id, "primary" if index == 0 else "supporting", 1.0 if index == 0 else 0.5),
                        )
                report["imported"]["mistakes"] += 1
            self._event(
                connection,
                student_id=student_id,
                kind="migration",
                detail=f"local-v1:{content_hash}",
                source_page="graph",
                revision=revision,
            )
            connection.execute(
                "UPDATE learner_state_meta SET local_v1_imported=1,local_v1_hash=? WHERE student_id=?",
                (content_hash, student_id),
            )
            report["revision"] = revision
            connection.execute(
                "INSERT INTO local_imports(student_id,content_hash,report_json,imported_at) VALUES(?,?,?,?)",
                (student_id, content_hash, _json(report), now),
            )
            return report
