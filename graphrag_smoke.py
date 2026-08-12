# -*- coding: utf-8 -*-
"""GraphRAG end-to-end smoke: intent route -> graph evidence -> LLM answer.

Requires the graph backend on :8000 and a configured DEEPSEEK_API_KEY.
Run: python graphrag_smoke.py
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import tutor_agent as ta
from llm import LLMClient


def main():
    client = LLMClient()
    context = ta.TurnContext("graphrag_smoke_student")

    question = "动态规划和分治有什么区别，它们都依赖递归吗？"
    forced = ta.route_intent(question, in_diagnostic=context.in_diagnostic)
    print(f"question: {question}\nroute: {forced or 'auto'}")
    messages = [
        {"role": "system", "content": ta.SYSTEM},
        {"role": "user", "content": question},
    ]
    reply = ta.run_turn(client, messages, forced_tool=forced, context=context)
    print(f"answer: {reply}\ncalled: {context.tool_log}")

    ok = (
        forced == "retrieve_graph_context"
        and "retrieve_graph_context" in context.tool_log
        and bool(reply)
    )
    print("GraphRAG E2E OK" if ok else "GraphRAG E2E FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
