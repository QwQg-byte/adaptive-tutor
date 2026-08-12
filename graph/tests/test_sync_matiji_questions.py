import copy
import json
import unittest

from scripts.sync_matiji_questions import (
    EXPECTED_IDS,
    OFFICIAL_KNOWLEDGE_LINKS,
    ORDERS,
    ParsedQuestion,
    html_to_text,
    merge_questions,
    normalize_difficulty,
    parse_question,
    validate_batch,
)


def question_payload(question_id="MC0577 "):
    return {
        "data": {
            "ojProblemEntity": {
                "ojNumber": question_id,
                "problemName": "测试题",
                "difficultyLevel": "星耀",
                "descriptionHtml": (
                    '<p>计算<span class="editormd-tex"><span class="katex">rendered'
                    '<annotation encoding="application/x-tex">x^2</annotation>'
                    "rendered</span></span>的值。</p>"
                ),
                "inputFormat": "一行输入。",
                "outputFormat": "一行输出。",
                "simpleArray": json.dumps(
                    [
                        {"sampleInput": "1", "sampleOutput": "2"},
                        {"sampleInput": "3", "sampleOutput": "4"},
                    ]
                ),
            },
            "ojProblemKnowledgeEntityList": [
                {"parentName": "数学", "knowledgeName": "拟阵"},
                {"parentName": "图论", "knowledgeName": "树上问题"},
            ],
            "passRateEntity": {"passRate": 0.139},
        }
    }


class SyncMatijiQuestionsTests(unittest.TestCase):
    def test_html_to_text_uses_tex_annotation_once(self):
        text = html_to_text(question_payload()["data"]["ojProblemEntity"]["descriptionHtml"])

        self.assertEqual(text, "计算$$x^2$$的值。")
        self.assertEqual(text.count("x^2"), 1)
        self.assertNotIn("rendered", text)

    def test_parse_question_strips_id_and_keeps_all_samples_and_tags(self):
        parsed = parse_question(question_payload(), 77)

        self.assertEqual(parsed.entity["id"], "MC0577")
        self.assertEqual(parsed.entity["difficulty"], "星耀")
        self.assertEqual(parsed.entity["pass_rate"], 13.9)
        self.assertEqual(parsed.entity["sample_input"], "1\n\n3")
        self.assertEqual(parsed.entity["sample_output"], "2\n\n4")
        self.assertEqual(
            parsed.entity["official_knowledge_tags"],
            ["数学/拟阵", "图论/树上问题"],
        )

    def test_difficulty_mapping_matches_existing_four_level_model(self):
        expected = {
            "青铜": "简单",
            "白银": "简单",
            "黄金": "中等",
            "钻石": "中等",
            "王者": "困难",
            "星耀": "星耀",
        }
        self.assertEqual({key: normalize_difficulty(key) for key in expected}, expected)
        with self.assertRaisesRegex(ValueError, "未知"):
            normalize_difficulty("传说")

    def test_validate_batch_rejects_wrong_question_number(self):
        questions = [
            ParsedQuestion(order=order, entity={"id": question_id}, knowledge_tags=())
            for order, question_id in zip(ORDERS, EXPECTED_IDS)
        ]
        questions[-1] = ParsedQuestion(
            order=ORDERS[-1], entity={"id": "MC9999"}, knowledge_tags=()
        )

        with self.assertRaisesRegex(ValueError, "题目编号不匹配"):
            validate_batch(questions)

    def test_merge_is_idempotent_and_links_all_official_categories(self):
        graph = {
            "metadata": {
                "total_entities": 3,
                "total_relationships": 1,
                "unique_questions": 1,
            },
            "entities": [
                {
                    "type": "Question",
                    "id": "OLD",
                    "category1": "数学",
                    "category2": "基础",
                },
                {"type": "Category", "id": "CATEGORY_数学", "name": "数学"},
                {"type": "Difficulty", "id": "DIFF_星耀", "level": "星耀"},
            ],
            "relationships": [
                {
                    "type": "REQUIRES",
                    "from": "OLD",
                    "to": "NODE_001",
                    "attributes": {"weight": 0.7},
                }
            ],
        }
        parsed = parse_question(question_payload(), 77)
        knowledge_ids = {
            "NODE_001",
            *(target for targets in OFFICIAL_KNOWLEDGE_LINKS.values() for target in targets),
        }

        first = merge_questions(graph, [parsed], knowledge_ids, updated_at="2026-08-04")
        after_first = copy.deepcopy(graph)
        second = merge_questions(graph, [parsed], knowledge_ids, updated_at="2026-08-04")

        self.assertEqual(first.added_entities["Question"], 1)
        self.assertIn("CATEGORY_数学_拟阵", {entity["id"] for entity in graph["entities"]})
        self.assertIn("CATEGORY_图论_树上问题", {entity["id"] for entity in graph["entities"]})
        relation_keys = {
            (relation["from"], relation["to"], relation["type"])
            for relation in graph["relationships"]
        }
        self.assertIn(("MC0577", "NODE_425", "REQUIRES"), relation_keys)
        self.assertIn(("MC0577", "NODE_130", "REQUIRES"), relation_keys)
        self.assertEqual(graph, after_first)
        self.assertFalse(second.changed)


if __name__ == "__main__":
    unittest.main()
