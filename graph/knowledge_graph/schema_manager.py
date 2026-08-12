"""Neo4j 5 schema management for the current production data model.

The database currently uses ``KnowledgeNode`` rather than the legacy
``KnowledgePoint`` label.  All schema objects are explicitly named so that
creation and removal are repeatable on Neo4j 5.x.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

try:
    from .neo4j_connector import Neo4jConnector
except ImportError:  # pragma: no cover - direct script compatibility
    from neo4j_connector import Neo4jConnector


logger = logging.getLogger(__name__)


CONSTRAINTS = (
    {
        "name": "knowledge_node_id_unique",
        "label": "KnowledgeNode",
        "property": "id",
        "statement": (
            "CREATE CONSTRAINT knowledge_node_id_unique IF NOT EXISTS "
            "FOR (n:KnowledgeNode) REQUIRE n.id IS UNIQUE"
        ),
    },
    {
        "name": "knowledge_node_node_id_unique",
        "label": "KnowledgeNode",
        "property": "node_id",
        "statement": (
            "CREATE CONSTRAINT knowledge_node_node_id_unique IF NOT EXISTS "
            "FOR (n:KnowledgeNode) REQUIRE n.node_id IS UNIQUE"
        ),
    },
    {
        "name": "question_id_unique",
        "label": "Question",
        "property": "id",
        "statement": (
            "CREATE CONSTRAINT question_id_unique IF NOT EXISTS "
            "FOR (q:Question) REQUIRE q.id IS UNIQUE"
        ),
    },
)


RANGE_INDEXES = (
    {
        "name": "knowledge_node_name_idx",
        "statement": (
            "CREATE RANGE INDEX knowledge_node_name_idx IF NOT EXISTS "
            "FOR (n:KnowledgeNode) ON (n.name)"
        ),
    },
    {
        "name": "knowledge_node_chapter_id_idx",
        "statement": (
            "CREATE RANGE INDEX knowledge_node_chapter_id_idx IF NOT EXISTS "
            "FOR (n:KnowledgeNode) ON (n.chapter_id)"
        ),
    },
    {
        "name": "question_difficulty_idx",
        "statement": (
            "CREATE RANGE INDEX question_difficulty_idx IF NOT EXISTS "
            "FOR (q:Question) ON (q.difficulty)"
        ),
    },
    {
        "name": "question_category1_idx",
        "statement": (
            "CREATE RANGE INDEX question_category1_idx IF NOT EXISTS "
            "FOR (q:Question) ON (q.category1)"
        ),
    },
    {
        "name": "question_category1_id_idx",
        "statement": (
            "CREATE RANGE INDEX question_category1_id_idx IF NOT EXISTS "
            "FOR (q:Question) ON (q.category1, q.id)"
        ),
    },
    {
        "name": "question_difficulty_id_idx",
        "statement": (
            "CREATE RANGE INDEX question_difficulty_id_idx IF NOT EXISTS "
            "FOR (q:Question) ON (q.difficulty, q.id)"
        ),
    },
)


FULLTEXT_INDEXES = (
    {
        "name": "content_search_fulltext",
        "statement": (
            "CREATE FULLTEXT INDEX content_search_fulltext IF NOT EXISTS "
            "FOR (n:KnowledgeNode|Chapter|Question) "
            "ON EACH [n.name, n.title, n.overview, n.description, n.content, "
            "n.category1, n.category2, n.section] "
            "OPTIONS {indexConfig: {`fulltext.analyzer`: 'cjk', "
            "`fulltext.eventually_consistent`: false}}"
        ),
    },
)


CREATE_STATEMENTS = tuple(
    item["statement"]
    for item in (*CONSTRAINTS, *RANGE_INDEXES, *FULLTEXT_INDEXES)
)
DROP_INDEX_STATEMENTS = tuple(
    f"DROP INDEX {item['name']} IF EXISTS"
    for item in (*FULLTEXT_INDEXES, *RANGE_INDEXES)
)
DROP_CONSTRAINT_STATEMENTS = tuple(
    f"DROP CONSTRAINT {item['name']} IF EXISTS" for item in CONSTRAINTS
)


class SchemaManager:
    """Create, inspect and remove only schema objects owned by this project."""

    ENTITY_TYPES = {
        "KnowledgeNode": {
            "properties": {
                "id": "string",
                "node_id": "string",
                "name": "string",
                "chapter_id": "integer",
            },
            "constraints": ["id", "node_id"],
            "indexes": ["name", "chapter_id"],
        },
        "Question": {
            "properties": {
                "id": "string",
                "name": "string",
                "difficulty": "string",
                "category1": "string",
                "category2": "string",
                "pass_rate": "string",
            },
            "constraints": ["id"],
            "indexes": [
                "difficulty",
                "category1",
                "(category1, id)",
                "(difficulty, id)",
            ],
        },
        "Chapter": {
            "properties": {"id": "string", "title": "string"},
            "constraints": [],
            "indexes": [],
        },
    }

    RELATIONSHIP_TYPES = {
        "REQUIRES": {"from": "Question", "to": "KnowledgeNode"},
        "PREREQUISITE": {"from": "KnowledgeNode", "to": "KnowledgeNode"},
        "BELONGS_TO": {"from": "KnowledgeNode", "to": "Chapter"},
        "RELATED_TO": {"from": "KnowledgeNode", "to": "KnowledgeNode"},
    }

    def __init__(self, connector: Neo4jConnector):
        self.connector = connector

    def validate_constraint_candidates(self) -> Dict[str, Dict[str, Any]]:
        """Report missing and duplicate values before unique constraints are made."""
        results: Dict[str, Dict[str, Any]] = {}
        for item in CONSTRAINTS:
            label = item["label"]
            prop = item["property"]
            query = f"""
            MATCH (n:{label})
            RETURN count(n) AS total,
                   count(n.{prop}) AS populated,
                   count(DISTINCT n.{prop}) AS distinct_values
            """
            rows = self.connector.execute_query(query)
            row = rows[0] if rows else {
                "total": 0,
                "populated": 0,
                "distinct_values": 0,
            }
            duplicate_count = row["populated"] - row["distinct_values"]
            results[item["name"]] = {
                **row,
                "missing": row["total"] - row["populated"],
                "duplicate_count": duplicate_count,
                "valid": duplicate_count == 0,
            }
        return results

    def create_all_constraints(self) -> Dict[str, bool]:
        results = {}
        for item in CONSTRAINTS:
            self.connector.execute_write(item["statement"])
            results[item["name"]] = True
        return results

    def create_all_indexes(self) -> Dict[str, bool]:
        results = {}
        for item in (*RANGE_INDEXES, *FULLTEXT_INDEXES):
            self.connector.execute_write(item["statement"])
            results[item["name"]] = True
        return results

    def drop_all_constraints(self) -> bool:
        for statement in DROP_CONSTRAINT_STATEMENTS:
            self.connector.execute_write(statement)
        return True

    def drop_all_indexes(self) -> bool:
        for statement in DROP_INDEX_STATEMENTS:
            self.connector.execute_write(statement)
        return True

    def wait_for_indexes(self, timeout_seconds: int = 300) -> None:
        if not 1 <= timeout_seconds <= 3600:
            raise ValueError("索引等待时间必须在 1 到 3600 秒之间")
        self.connector.execute_query(
            "CALL db.awaitIndexes($timeout_seconds)",
            {"timeout_seconds": timeout_seconds},
            timeout=float(timeout_seconds + 5),
        )

    def initialize_schema(self, timeout_seconds: int = 300) -> bool:
        validation = self.validate_constraint_candidates()
        invalid = [name for name, result in validation.items() if not result["valid"]]
        if invalid:
            raise ValueError(f"唯一约束候选字段存在重复值: {', '.join(invalid)}")

        self.create_all_constraints()
        self.create_all_indexes()
        self.wait_for_indexes(timeout_seconds)
        logger.info("Neo4j 5 Schema 初始化完成")
        return True

    def get_schema_status(self) -> Dict[str, Any]:
        constraints = self.connector.execute_query(
            "SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, "
            "properties, ownedIndex RETURN * ORDER BY name"
        )
        indexes = self.connector.execute_query(
            "SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, "
            "properties, state, populationPercent, owningConstraint "
            "RETURN * ORDER BY name"
        )
        managed_names = {
            item["name"] for item in (*CONSTRAINTS, *RANGE_INDEXES, *FULLTEXT_INDEXES)
        }
        return {
            "constraints": [row for row in constraints if row["name"] in managed_names],
            "indexes": [row for row in indexes if row["name"] in managed_names],
        }

    def get_schema_definition(self) -> Dict[str, Any]:
        return {
            "entity_types": self.ENTITY_TYPES,
            "relationship_types": self.RELATIONSHIP_TYPES,
            "constraints": CONSTRAINTS,
            "range_indexes": RANGE_INDEXES,
            "fulltext_indexes": FULLTEXT_INDEXES,
        }

    def export_schema_to_cypher(self, output_file: str | Path | None = None) -> str:
        script = ";\n".join(CREATE_STATEMENTS) + ";\n"
        if output_file:
            Path(output_file).write_text(script, encoding="utf-8", newline="\n")
        return script

    def print_schema_info(self) -> None:
        for label, config in self.ENTITY_TYPES.items():
            print(f"{label}: constraints={config['constraints']}, indexes={config['indexes']}")
        print("fulltext: content_search_fulltext (cjk)")


if __name__ == "__main__":
    with Neo4jConnector() as connector:
        manager = SchemaManager(connector)
        manager.initialize_schema()
        manager.print_schema_info()
