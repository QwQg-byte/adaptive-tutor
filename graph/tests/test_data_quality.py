import json
import tempfile
import unittest
from pathlib import Path

from scripts.data_quality_report import build_report


class DataQualityReportTests(unittest.TestCase):
    def test_report_detects_duplicates_invalid_edges_orphans_and_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            knowledge_file = root / "knowledge.json"
            question_file = root / "questions.json"
            knowledge_file.write_text(
                json.dumps(
                    {
                        "metadata": {"total_entities": 3, "total_relationships": 3},
                        "entities": [
                            {"type": "Chapter", "id": "CHAP_1", "name": "第1章"},
                            {"type": "KnowledgeNode", "id": "NODE_1", "overview": "概述"},
                            {"type": "KnowledgeNode", "id": "NODE_1", "overview": "重复"},
                        ],
                        "relationships": [
                            {"type": "BELONGS_TO", "source": "NODE_1", "target": "CHAP_1"},
                            {"type": "BELONGS_TO", "source": "NODE_1", "target": "CHAP_1"},
                            {"type": "REQUIRES", "source": "NODE_1", "target": "MISSING"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            question_file.write_text(
                json.dumps(
                    {
                        "metadata": {"total_entities": 1, "total_relationships": 0},
                        "entities": [{"type": "Question", "id": "MT1", "pass_rate": 50}],
                        "relationships": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report = build_report(knowledge_file, question_file)

        self.assertEqual(report["summary"]["error_count"], 3)
        self.assertIn("NODE_1", report["issues"]["duplicate_entity_ids"])
        self.assertEqual(len(report["issues"]["duplicate_relationships"]), 1)
        self.assertEqual(report["issues"]["invalid_relationship_count"], 1)
        self.assertEqual(report["coverage"]["knowledge_nodes"]["with_chapter"], 1)
        self.assertEqual(report["coverage"]["questions"]["with_pass_rate"], 1)


if __name__ == "__main__":
    unittest.main()
