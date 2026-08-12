# -*- coding: utf-8 -*-
"""学情诊断 —— Phase 1。

策略（保守传播，不逐点考）：
- 挑靠下游的"代表节点"出题；
- 答对 → 该节点按真题记为掌握(record)，且沿 PREREQUISITE 边把**直接前置**软置信到
  一个低于阈值的起点(SEED_PREREQ)：给个高起点、不当满分，留余量让后续真题再确认；
- 答错 → 只记该节点这次失败，前置不动（下一题"退一层"去考它的前置）。

只传播一跳直接前置，不级联整棵树——这是刻意的稳妥选择：一道下游题的信号
不足以断定所有远端祖先都会了。远端前置留给后续代表题各自覆盖。
"""
import config
import graph_tools
from graph_client import GraphClient

_graph = GraphClient()

# 答对下游题时，给直接前置的软置信起点（< MASTERY_THRESHOLD，留余量）
SEED_PREREQ = 0.55
# 代表节点答对时给它自己的掌握度（真题 record 走 EMA，这里额外托底到阈值）
SEED_PROBE = config.MASTERY_THRESHOLD


# 诊断代表题：一批靠下游、有配套题、覆盖不同算法/结构分支的锚点。
# 答对任一个都能沿前置边一次性点亮一片上游，做到"少考多推断"。
PROBE_NODES = [
    "动态规划", "递归算法设计", "分治法", "穷举法", "二分查找", "线性表", "图",
]


def _unwrap(r):
    if isinstance(r, dict) and "data" in r:
        return r["data"]
    return r


def pick_probe(student_id: str):
    """挑一个该生还没诊断过的代表节点，返回 {id,name}；都测过则返回 None。"""
    lm = graph_tools._learner
    tested = {e["node_id"] for e in lm.history(student_id, limit=200)
              if e.get("kind") == "diagnose"}
    for name in PROBE_NODES:
        node = graph_tools.resolve_knowledge_node(name)
        if node and node["id"] not in tested:
            return node
    return None


def probe_question(node_id: str):
    """取代表节点下的一道题（挑一道中等难度的当摸底题）。失败返回 None。"""
    try:
        data = _unwrap(_graph.questions_of_knowledge(node_id)) or []
        qs = data if isinstance(data, list) else data.get("questions", [])
        if not qs:
            return None
        mid = [q for q in qs if q.get("difficulty") in ("中等", "简单")]
        return (mid or qs)[0]
    except Exception:
        return None


def start(student_id: str):
    """开一轮诊断：挑代表节点 + 出一道题。返回 {probe, question} 或 {done:True}。"""
    node = pick_probe(student_id)
    if not node:
        return {"done": True, "message": "代表题都测过了，画像已初步建立。"}
    q = probe_question(node["id"])
    return {"done": False, "probe": node, "question": q}


def direct_prerequisites(node_name: str):
    """取某知识点的直接前置 [{id,name}]。失败返回 []。"""
    try:
        data = _unwrap(_graph.dependencies(node_name)) or {}
        pres = data.get("prerequisites", []) if isinstance(data, dict) else []
        return [{"id": p["id"], "name": p.get("name", "")}
                for p in pres if isinstance(p, dict) and p.get("id")]
    except Exception:
        return []


def apply_diagnostic_answer(student_id: str, node_id: str, node_name: str, correct: bool):
    """把一道诊断题的对错落进画像，并按策略传播。返回本次影响摘要。"""
    lm = graph_tools._learner
    # 1) 代表节点本身：走真题记录（进 attempts + EMA）
    m = lm.record(student_id, node_id, node_name, correct=correct, kind="diagnose")
    touched = [{"id": node_id, "name": node_name, "mastery": round(m, 3), "role": "probe"}]

    # 2) 答对 → 托底代表节点到阈值 + 软置信直接前置
    if correct:
        m2 = lm.seed(student_id, node_id, node_name, SEED_PROBE, detail="probe_correct")
        touched[0]["mastery"] = round(m2, 3)
        for p in direct_prerequisites(node_name):
            mp = lm.seed(student_id, p["id"], p["name"], SEED_PREREQ)
            touched.append({"id": p["id"], "name": p["name"],
                            "mastery": round(mp, 3), "role": "prereq_seeded"})
    return {"correct": correct, "touched": touched}