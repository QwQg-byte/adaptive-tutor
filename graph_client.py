# -*- coding: utf-8 -*-
"""知识图谱客户端 —— 把图谱后端封成 Agent 能调的工具。

对应图谱 API（prefix /api/v1）：
  POST /path/plan                      个性化学习计划（吃 mastered/completed/难度）
  GET  /graph/knowledge-points         知识点列表
  GET  /graph/knowledge-point/{id}/questions   某知识点下的题
  GET  /graph/question/{qid}/knowledge 题反查知识点
  GET  /graph/node/{id}/neighbors      节点邻居
  POST /search/                        按关键词/类型搜节点
"""
import requests

import config


class GraphClient:
    def __init__(self, base_url: str = None, timeout: float = None):
        self.base = (base_url or config.GRAPH_BASE_URL).rstrip("/")
        self.timeout = timeout or config.GRAPH_TIMEOUT_SECONDS

    def _get(self, path: str, params: dict = None):
        r = requests.get(f"{self.base}{path}", params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, payload: dict):
        r = requests.post(f"{self.base}{path}", json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # ---- 路径规划（赛题能力②，引擎现成）----
    def generate_plan(self, target: str, mastered=None, completed=None,
                      difficulty_preference: str = "balanced",
                      questions_per_step: int = 3, max_depth: int = 6):
        """给目标知识点生成个性化学习计划，自动裁掉已掌握前置。"""
        return self._post("/path/plan", {
            "target": target,
            "mastered": mastered or [],
            "completed": completed or [],
            "difficulty_preference": difficulty_preference,
            "questions_per_step": questions_per_step,
            "max_depth": max_depth,
        })

    # ---- 地图查询 ----
    def list_knowledge_points(self, limit: int = 100):
        return self._get("/graph/knowledge-points", {"limit": limit})

    def node_neighbors(self, node_id: str, limit: int = 30, relationship_types=None):
        params = {"limit": limit}
        if relationship_types:
            params["relationship_types"] = ",".join(relationship_types)
        return self._get(f"/graph/node/{node_id}/neighbors", params)

    def knowledge_point_detail(self, knowledge_id: str):
        """取知识点完整属性、直接语义关系和所属章节。"""
        return self._get(f"/graph/knowledge-point/{knowledge_id}")

    def questions_of_knowledge(self, knowledge_id: str):
        return self._get(f"/graph/knowledge-point/{knowledge_id}/questions")

    def knowledge_of_question(self, question_id: str):
        return self._get(f"/graph/question/{question_id}/knowledge")

    def dependencies(self, knowledge_name: str, depth: int = 1):
        """取某知识点的直接前置(prerequisites)与后继(next)。用于诊断时沿前置边传播。"""
        return self._get(f"/path/dependencies/{knowledge_name}", {"depth": depth})

    def search(self, keyword: str, node_types=None, limit: int = 50):
        return self._post("/search/", {
            "keyword": keyword,
            "node_types": node_types,
            "limit": limit,
        })

    def health(self):
        """连通性检查：拉一次知识点列表，能回就算通。"""
        data = self._get("/graph/knowledge-points", {"limit": 1})
        return bool(data)
