# -*- coding: utf-8 -*-
"""主脑对话冒烟：喂几句自然语言，看 Agent 会不会自己调工具。

需 .env 填好 DEEPSEEK_API_KEY，且本地图谱后端在跑（8000）。
跑：python agent_smoke.py
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

from llm import LLMClient
from tutor_agent import SYSTEM, TurnContext, route_intent, run_turn


def main():
    client = LLMClient()
    student_id = "smoke_stu_" + str(id(client))[-4:]
    print(f"LLM={client.provider}，学生已设。开始对话冒烟。\n")

    messages = [{"role": "system", "content": SYSTEM}]
    in_diagnostic = False
    called = []
    turns = [
        "我想学动态规划，帮我规划一条学习路径。",
        "我刚做了一道递归的题，做对了。",
        "看看我现在的能力画像。",
    ]
    for t in turns:
        forced = route_intent(t, in_diagnostic=in_diagnostic)
        print(f"你：{t}   [路由→{forced or 'auto'}]")
        messages.append({"role": "user", "content": t})
        context = TurnContext(student_id, in_diagnostic=in_diagnostic)
        reply = run_turn(client, messages, forced_tool=forced, context=context)
        in_diagnostic = context.in_diagnostic
        called.extend(context.tool_log)
        print(f"    ↳ 工具调用: {context.tool_log or '无'}")
        print(f"伴学 Agent：{reply}\n")

    print("=== 本轮共调用工具:", called or "（一个都没调，可能没连上）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
