# -*- coding: utf-8 -*-
"""诊断流程 · 真对话冒烟：摸底 → 答对 → 看路径变短，全走 DeepSeek + 路由。

需 .env 有 key、图谱后端在跑。跑：python diagnose_agent_smoke.py
"""
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

import graph_tools
import tutor_agent as ta
from learner_model import LearnerModel
from llm import LLMClient


def main():
    client = LLMClient()
    tmp = os.path.join(tempfile.mkdtemp(prefix="diagA_"), "t.db")
    graph_tools._learner = LearnerModel(db_path=tmp)
    student_id = "diagA_stu"

    messages = [{"role": "system", "content": ta.SYSTEM}]
    in_diagnostic = False
    called = []
    turns = [
        "先给我做个摸底，测测我的水平。",
        "这题我会，做对了。",
        "现在我想学动态规划，帮我规划路径。",
    ]
    for t in turns:
        forced = ta.route_intent(t, in_diagnostic=in_diagnostic)
        print(f"\n你：{t}   [路由→{forced or 'auto'}]")
        messages.append({"role": "user", "content": t})
        context = ta.TurnContext(student_id, in_diagnostic=in_diagnostic)
        reply = ta.run_turn(client, messages, forced_tool=forced, context=context)
        in_diagnostic = context.in_diagnostic
        called.extend(context.tool_log)
        print(f"    ↳ 工具: {context.tool_log}  [诊断中={in_diagnostic}]")
        print(f"伴学 Agent：{reply[:500]}")

    print("\n=== 工具调用序列:", called)
    prof = graph_tools._learner.profile(student_id)
    print("最终画像：跟踪", prof["total_tracked"], "个，已掌握", prof["mastered"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
