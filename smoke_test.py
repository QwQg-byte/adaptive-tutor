# -*- coding: utf-8 -*-
"""阶段 0 冒烟测试：只验图谱连通 + 路径引擎可调，不需要 LLM key。

    python smoke_test.py
"""
import sys

from graph_client import GraphClient

sys.stdout.reconfigure(encoding="utf-8")


def main():
    g = GraphClient()
    print(f"图谱地址：{g.base}")

    print("\n[1] 连通性检查 ...")
    try:
        ok = g.health()
        print("    OK" if ok else "    连上了但没数据")
    except Exception as exc:  # noqa: BLE001
        print(f"    失败：{exc}")
        print("    —— 图谱后端没起，或 GRAPH_BASE_URL 不对。检查 .env。")
        return

    print("\n[2] 拉知识点（前 5 条）...")
    try:
        kp = g.list_knowledge_points(limit=5)
        print(f"    返回：{str(kp)[:300]}")
    except Exception as exc:  # noqa: BLE001
        print(f"    失败：{exc}")

    print("\n[3] 生成一次学习计划（取一个真实知识点当目标）...")
    try:
        kp = g.list_knowledge_points(limit=1)
        rows = kp.get("data") if isinstance(kp, dict) else None
        target = None
        if rows:
            first = rows[0]
            target = first.get("name") or first.get("label") or first.get("id")
        target = target or "数据"
        plan = g.generate_plan(target=target, questions_per_step=2)
        data = plan.get("data") if isinstance(plan, dict) else None
        steps = data.get("total_steps") if isinstance(data, dict) else "?"
        print(f"    target='{target}' -> 计划共 {steps} 步")
        print(f"    返回：{str(plan)[:300]}")
    except Exception as exc:  # noqa: BLE001
        print(f"    失败：{exc}")

    print("\n完成。")


if __name__ == "__main__":
    main()
