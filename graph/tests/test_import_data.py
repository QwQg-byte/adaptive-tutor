"""Tests for UNWIND batching and import failure reporting."""

import json
import tempfile
import unittest
from pathlib import Path

from import_data import (
    import_knowledge_nodes,
    import_relationships,
    validate_import_data,
    write_failure_report,
)
from knowledge_graph.neo4j_exceptions import Neo4jConnectionError, Neo4jQueryError


class FakeConnector:
    def __init__(
        self,
        fail_on_row_id=None,
        omit_row_id=None,
        connection_failure=False,
    ):
        self.fail_on_row_id = fail_on_row_id
        self.omit_row_id = omit_row_id
        self.connection_failure = connection_failure
        self.calls = []

    def execute_write_records(self, query, parameters):
        rows = parameters["rows"]
        self.calls.append((query, list(rows)))
        if self.connection_failure:
            raise Neo4jConnectionError("simulated outage")
        if self.fail_on_row_id and any(
            row["row_id"] == self.fail_on_row_id for row in rows
        ):
            raise Neo4jQueryError("simulated row failure")
        return [
            {"row_id": row["row_id"]}
            for row in rows
            if row["row_id"] != self.omit_row_id
        ]


class ImportDataTests(unittest.TestCase):
    def test_official_matiji_metadata_passes_import_validation(self):
        data = {
            "entities": [
                {
                    "type": "Question",
                    "id": "MC0577",
                    "official_difficulty": "白银",
                    "official_knowledge_tags": ["语言基础/字符串"],
                }
            ],
            "relationships": [
                {
                    "type": "REQUIRES",
                    "from": "MC0577",
                    "to": "NODE_082",
                    "attributes": {"official_tag": "语言基础/字符串"},
                }
            ],
        }

        validate_import_data(data, "test")

    def test_string_lists_remain_native_properties(self):
        data = {
            "entities": [
                {
                    "id": "NODE_1",
                    "type": "KnowledgeNode",
                    "tags": ["串", "模式匹配"],
                }
            ]
        }
        connector = FakeConnector()

        import_knowledge_nodes(connector, data, "test", 10, [])

        properties = connector.calls[0][1][0]["properties"]
        self.assertEqual(properties["tags"], ["串", "模式匹配"])

    def test_entities_are_imported_in_unwind_batches(self):
        data = {
            "entities": [
                {"id": "NODE_1", "type": "KnowledgeNode", "name": "one"},
                {"id": "NODE_2", "type": "KnowledgeNode", "name": "two"},
                {"id": "NODE_3", "type": "KnowledgeNode", "name": "three"},
            ]
        }
        connector = FakeConnector()
        failures = []

        stats = import_knowledge_nodes(connector, data, "test", 2, failures)

        self.assertEqual(stats, {"KnowledgeNode": 3})
        self.assertEqual(len(connector.calls), 2)
        self.assertTrue(all("UNWIND $rows" in call[0] for call in connector.calls))
        self.assertEqual(failures, [])

    def test_bad_entity_is_isolated_without_losing_good_rows(self):
        data = {
            "entities": [
                {"id": "NODE_1", "type": "KnowledgeNode"},
                {"id": "NODE_BAD", "type": "KnowledgeNode"},
                {"id": "NODE_3", "type": "KnowledgeNode"},
            ]
        }
        bad_row_id = "test:entity:2"
        connector = FakeConnector(fail_on_row_id=bad_row_id)
        failures = []

        stats = import_knowledge_nodes(connector, data, "test", 3, failures)

        self.assertEqual(stats, {"KnowledgeNode": 2})
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["id"], "NODE_BAD")
        self.assertEqual(failures[0]["reason"], "query_error")

    def test_missing_relationship_endpoint_is_reported(self):
        data = {
            "relationships": [
                {"from": "NODE_1", "to": "NODE_2", "type": "PREREQUISITE"},
                {"from": "NODE_2", "to": "MISSING", "type": "PREREQUISITE"},
            ]
        }
        missing_row_id = "test:relationship:2"
        connector = FakeConnector(omit_row_id=missing_row_id)
        failures = []

        stats = import_relationships(connector, data, "test", 100, failures)

        self.assertEqual(stats, {"PREREQUISITE": 1})
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["to_id"], "MISSING")
        self.assertEqual(failures[0]["reason"], "endpoint_not_found")

    def test_connection_failure_aborts_without_bisecting(self):
        data = {
            "entities": [
                {"id": "NODE_1", "type": "KnowledgeNode"},
                {"id": "NODE_2", "type": "KnowledgeNode"},
            ]
        }
        connector = FakeConnector(connection_failure=True)

        with self.assertRaises(Neo4jConnectionError):
            import_knowledge_nodes(connector, data, "test", 2, [])

        self.assertEqual(len(connector.calls), 1)

    def test_failure_report_is_written_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "nested" / "failures.json"
            write_failure_report(
                report_path,
                [{"reason": "endpoint_not_found"}],
                {"total_nodes": 2},
            )

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["failure_count"], 1)
            self.assertEqual(report["verification"]["total_nodes"], 2)
            self.assertFalse(report_path.with_suffix(".json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
