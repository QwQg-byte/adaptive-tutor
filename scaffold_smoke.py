# -*- coding: utf-8 -*-
"""阶段3 脚手架辅导 · 真对话冒烟：讲解 + 卡住求助，全走 DeepSeek + 路由。

验证：命中辅导意图 → 强制先调 get_knowledge_detail 接地 → 再给分层提示。
需 .env 有 key、图谱后端在跑。跑：python scaffold_smoke.py
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
    tmp = os.path.join(tempfile.mkdtemp(prefix="scaffold_"), "t.db")
    graph_tools._learner = LearnerModel(db_path=tmp)
    student_id = "scaffold_stu"

    messages = [{"role": "system", "content": ta.SYSTEM}]
    in_diagnostic = False
    called = []
    turns = [
        "讲讲动态规划吧，我想理解它。",
        "还是有点懵，动态规划那题我没思路，给点提示。",
    ]
    for t in turns:
        forced = ta.route_intent(t, in_diagnostic=in_diagnostic)
        print(f"\n你：{t}   [路由→{forced or 'auto'}]")
        messages.append({"role": "user", "content": t})
        context = ta.TurnContext(student_id, in_diagnostic=in_diagnostic)
        reply = ta.run_turn(client, messages, forced_tool=forced, context=context)
        in_diagnostic = context.in_diagnostic
        called.extend(context.tool_log)
        print(f"    ↳ 工具: {context.tool_log}")
        print(f"伴学 Agent：{reply[:600]}")

    print("\n=== 工具调用序列:", called)
    ok = called.count("get_knowledge_detail") >= 1
    print("接地工具被调用：", "✅" if ok else "❌ 未接地！")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
