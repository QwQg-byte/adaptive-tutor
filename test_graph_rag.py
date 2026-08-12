# -*- coding: utf-8 -*-
"""Offline tests for GraphRAG retrieval; no Neo4j or LLM key required."""
import unittest

import graph_rag
import tutor_agent


class FakeGraph:
    nodes = {
        "动态规划": {
            "id": "NODE_DP", "name": "动态规划", "label": "KnowledgeNode",
            "overview": "把重叠子问题的结果保存起来。", "search_score": 9.0,
        },
        "分治法": {
            "id": "NODE_DC", "name": "分治法", "label": "KnowledgeNode",
            "overview": "分解为相互独立的子问题。", "search_score": 8.0,
        },
    }

    def search(self, keyword, node_types=None, limit=50):
        # Force query splitting so the test covers multi-entity recovery.
        if keyword == "动态规划和分治有什么区别":
            return {"data": [
                self.nodes["动态规划"],
                {"id": "NODE_TSP", "name": "旅行商问题（动态规划）",
                 "label": "KnowledgeNode", "search_score": 7.0},
            ]}
        if keyword in self.nodes:
            return {"data": [self.nodes[keyword]]}
        if "动态规划" == keyword:
            return {"data": [self.nodes["动态规划"]]}
        if "分治" == keyword:
            return {"data": [self.nodes["分治法"]]}
        return {"data": []}

    def knowledge_point_detail(self, node_id):
        node = next(value for value in self.nodes.values() if value["id"] == node_id)
        return {"data": {
            "knowledge_point": node,
            "related_nodes": [],
            "chapter_info": None,
        }}

    def dependencies(self, name, depth=1):
        if name == "动态规划":
            return {"data": {
                "prerequisites": [{"id": "NODE_RECUR", "name": "递归"}],
                "next": [{"id": "NODE_KNAP", "name": "背包问题"}],
            }}
        return {"data": {"prerequisites": [], "next": []}}


class BrokenDetailGraph(FakeGraph):
    def knowledge_point_detail(self, node_id):
        raise RuntimeError("detail unavailable")


class GraphRagTests(unittest.TestCase):
    def test_prerequisite_question_extracts_both_entities(self):
        terms = graph_rag.query_terms("为什么学习动态规划前要先学递归")
        self.assertIn("动态规划", terms)
        self.assertIn("递归", terms)

    def test_comparison_retrieves_both_anchors_and_bounded_subgraph(self):
        result = graph_rag.retrieve(
            "动态规划和分治有什么区别",
            FakeGraph(),
            mastery_by_id={"NODE_RECUR": 0.55},
            max_nodes=4,
        )
        self.assertTrue(result["found"])
        self.assertEqual(
            {anchor["name"] for anchor in result["anchors"]},
            {"动态规划", "分治法"},
        )
        self.assertLessEqual(len(result["nodes"]), 4)
        recursive = next(node for node in result["nodes"] if node["id"] == "NODE_RECUR")
        self.assertEqual(recursive["learner_state"], "likely_known")
        self.assertIn(
            {"source": "NODE_DP", "target": "NODE_RECUR", "type": "PREREQUISITE"},
            result["edges"],
        )
        self.assertTrue(all(node.get("evidence_id") for node in result["nodes"]))

    def test_detail_failure_keeps_search_evidence(self):
        result = graph_rag.retrieve("动态规划为什么需要递归", BrokenDetailGraph())
        self.assertTrue(result["found"])
        self.assertTrue(result.get("partial_errors"))
        self.assertTrue(any(node["name"] == "动态规划" for node in result["nodes"]))

    def test_no_hit_is_explicit(self):
        result = graph_rag.retrieve("完全不存在的主题", FakeGraph())
        self.assertFalse(result["found"])
        self.assertEqual(result["reason"], "no_knowledge_node")

    def test_relationship_intent_routes_to_graph_rag(self):
        self.assertEqual(
            tutor_agent.route_intent("动态规划和分治有什么区别"),
            "retrieve_graph_context",
        )
        self.assertEqual(tutor_agent.route_intent("讲讲动态规划"), "get_knowledge_detail")


if __name__ == "__main__":
    unittest.main()
