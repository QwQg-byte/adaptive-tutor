# -*- coding: utf-8 -*-
"""端到端裁剪冒烟：画像标记已掌握 → generate_learning_plan 路径应变短。

需本地图谱后端在跑（8000）。跑：python prune_smoke.py
"""
import json
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

import graph_tools
from graph_client import GraphClient
from learner_model import LearnerModel


def unwrap(r):
    """图谱统一响应 {success,message,data} → data；否则原样。"""
    if isinstance(r, dict) and "data" in r and set(r.keys()) <= {"success", "message", "data", "code"}:
        return r["data"]
    return r


def get_steps(plan):
    p = unwrap(plan)
    if isinstance(p, list):
        return p
    if isinstance(p, dict):
        return p.get("path") or p.get("steps") or p.get("plan") or p.get("nodes") or []
    return []


def main():
    g = GraphClient()
    print("base:", g.base)

    items = unwrap(g.list_knowledge_points(limit=300)) or []
    print("knowledge points:", len(items))
    if items:
        it0 = items[0]
        print("node_type values sample:", sorted({str(i.get("node_type") or i.get("type")) for i in items[:50]}))
        print("item0 id/node_id/name:", it0.get("id"), "/", it0.get("node_id"), "/", it0.get("name"))

    # find a target with a baseline plan of >= 4 steps
    target = base_steps = None
    tried = 0
    for it in items:
        for key in ("node_id", "name", "id"):
            val = it.get(key)
            if not val:
                continue
            tried += 1
            try:
                steps = get_steps(g.generate_plan(target=val, mastered=[]))
            except Exception:
                continue
            if len(steps) >= 4:
                target, base_steps = val, steps
                break
        if target:
            break
    print(f"tried {tried} lookups; chosen target: {target!r}; baseline steps: {len(base_steps) if base_steps else None}")

    if not target:
        # dump one raw plan so we can see its real shape
        v = items[0].get("node_id") or items[0].get("name")
        raw = g.generate_plan(target=v, mastered=[])
        print("RAW plan for", v, ":", json.dumps(raw, ensure_ascii=False)[:800])
        return 1

    print("step0 keys:", list(base_steps[0].keys()) if isinstance(base_steps[0], dict) else base_steps[0])
    ids = [s.get("node_id") or s.get("id") or s.get("knowledge_id") for s in base_steps if isinstance(s, dict)]
    ids = [i for i in ids if i][:-1]  # all but the target
    to_master = ids[: max(1, len(ids) // 2)]
    print("marking mastered:", to_master)

    tmp = os.path.join(tempfile.mkdtemp(prefix="prune_"), "t.db")
    lm = LearnerModel(db_path=tmp)
    graph_tools._learner = lm
    student_id = "prune_stu"
    for nid in to_master:
        for _ in range(3):
            lm.record(student_id, nid, "", True)
    print("mastered_ids from model:", lm.mastered_ids(student_id))

    out = json.loads(
        graph_tools.dispatch(
            "generate_learning_plan", {"target": target}, student_id=student_id
        )
    )
    steps2 = get_steps(out)
    n1, n2 = len(base_steps), len(steps2)
    print(f"baseline={n1}  pruned={n2}")
    print("PRUNE OK ✅" if n2 < n1 else f"NO PRUNE — {str(out)[:300]}")
    return 0 if n2 < n1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
