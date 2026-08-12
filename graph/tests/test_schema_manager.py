"""Tests for the idempotent Neo4j 5 Schema definition."""

import unittest

from knowledge_graph.schema_manager import (
    CONSTRAINTS,
    FULLTEXT_INDEXES,
    RANGE_INDEXES,
    SchemaManager,
)


class FakeConnector:
    def __init__(self, *, duplicate_count=0):
        self.duplicate_count = duplicate_count
        self.writes = []
        self.reads = []

    def execute_write(self, query, parameters=None, **kwargs):
        self.writes.append((query, parameters))
        return True

    def execute_query(self, query, parameters=None, **kwargs):
        self.reads.append((query, parameters))
        if query.lstrip().startswith("MATCH"):
            return [{
                "total": 10,
                "populated": 10,
                "distinct_values": 10 - self.duplicate_count,
            }]
        if query.startswith("SHOW CONSTRAINTS") or query.startswith("SHOW INDEXES"):
            return []
        return []


class SchemaManagerTests(unittest.TestCase):
    def test_apply_statements_are_named_and_idempotent(self):
        connector = FakeConnector()
        manager = SchemaManager(connector)

        manager.initialize_schema()

        statements = [query for query, _ in connector.writes]
        self.assertEqual(
            len(statements),
            len(CONSTRAINTS) + len(RANGE_INDEXES) + len(FULLTEXT_INDEXES),
        )
        self.assertTrue(all("IF NOT EXISTS" in query for query in statements))
        self.assertTrue(any("'cjk'" in query for query in statements))

    def test_duplicate_candidate_stops_before_schema_writes(self):
        connector = FakeConnector(duplicate_count=1)
        manager = SchemaManager(connector)

        with self.assertRaises(ValueError):
            manager.initialize_schema()

        self.assertEqual(connector.writes, [])

    def test_drop_only_uses_named_if_exists_statements(self):
        connector = FakeConnector()
        manager = SchemaManager(connector)

        manager.drop_all_indexes()
        manager.drop_all_constraints()

        statements = [query for query, _ in connector.writes]
        self.assertTrue(all(" IF EXISTS" in query for query in statements))
        self.assertTrue(all("DROP INDEX" in query or "DROP CONSTRAINT" in query for query in statements))


if __name__ == "__main__":
    unittest.main()
