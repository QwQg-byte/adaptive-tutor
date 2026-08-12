# -*- coding: utf-8 -*-
"""诊断冒烟：答对一道靠下游的代表题 → 目标路径应立刻变短。

需本地图谱后端在跑（8000）。跑：python diagnose_smoke.py
验证闭环：diagnose_answer(对) → 代表节点+直接前置进画像 → generate_learning_plan 裁掉它们。
"""
import json
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

import graph_tools
from graph_client import GraphClient
from learner_model import LearnerModel

PASS, FAIL = "✅", "❌"


def steps_of(plan):
    d = plan.get("data", plan) if isinstance(plan, dict) else plan
    if isinstance(d, dict):
        return d.get("path") or d.get("steps") or []
    return d if isinstance(d, list) else []


def main():
    g = GraphClient()
    print("base:", g.base)

    tmp = os.path.join(tempfile.mkdtemp(prefix="diag_"), "t.db")
    graph_tools._learner = LearnerModel(db_path=tmp)
    student_id = "diag_stu"

    target = "动态规划"
    probe = "递归算法设计"  # 通往动态规划路径上的一个靠下游代表点

    base_steps = steps_of(g.generate_plan(target=target, mastered=[]))
    print(f"\n诊断前：通往「{target}」基线路径 = {len(base_steps)} 步")

    # 学生答对了代表题
    out = json.loads(
        graph_tools.dispatch(
            "diagnose_answer",
            {"node_name": probe, "correct": True},
            student_id=student_id,
        )
    )
    touched = out.get("touched", [])
    print(f"\n诊断：答对「{probe}」→ 影响 {len(touched)} 个节点：")
    for t in touched:
        print(f"   {t['role']:14s} {t['id']:9s} {t['name']}  mastery={t['mastery']}")

    prof = graph_tools._learner.profile(student_id)
    print(f"\n画像：已掌握 {len(prof['mastered'])} 个 {prof['mastered']}；跟踪 {prof['total_tracked']} 个")

    after = json.loads(
        graph_tools.dispatch(
            "generate_learning_plan", {"target": target}, student_id=student_id
        )
    )
    after_steps = steps_of(after)
    print(f"\n诊断后：通往「{target}」路径 = {len(after_steps)} 步")

    ok = True
    ok &= _c(len(touched) >= 2, "答对代表题传播到 ≥2 个节点（自身+直接前置）")
    ok &= _c(probe_id_in(touched) in prof["mastered"], "代表节点进入 mastered")
    ok &= _c(len(after_steps) < len(base_steps),
             f"路径变短：{len(base_steps)} → {len(after_steps)}")
    print("\n全部通过 🎉" if ok else "\n有用例失败，见上。")
    return 0 if ok else 1


def probe_id_in(touched):
    for t in touched:
        if t["role"] == "probe":
            return t["id"]
    return None


def _c(cond, label):
    print(f"{PASS if cond else FAIL} {label}")
    return cond


if __name__ == "__main__":
    raise SystemExit(main())
