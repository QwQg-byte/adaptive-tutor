# -*- coding: utf-8 -*-
"""LLM 抽象层。

现接 DeepSeek（OpenAI 兼容）。星火 provider 预留接口，未实现——
分叉点 B：确认赛题是否强制接星火后再补 SparkClient。
换 provider 只改 .env 的 LLM_PROVIDER，上层 Agent 代码不动。
"""
from openai import OpenAI

import config


class LLMClient:
    """统一的对话+工具调用接口，屏蔽底层 provider 差异。"""

    def __init__(self):
        provider = config.LLM_PROVIDER.lower()
        if provider == "deepseek":
            if not config.DEEPSEEK_API_KEY:
                raise RuntimeError("缺少 DEEPSEEK_API_KEY，请在 .env 或环境变量里配置。")
            self._client = OpenAI(
                base_url=config.DEEPSEEK_BASE_URL,
                api_key=config.DEEPSEEK_API_KEY,
            )
            self._model = config.DEEPSEEK_MODEL
        elif provider == "spark":
            raise NotImplementedError(
                "星火 provider 尚未实现（分叉点 B）。确认赛题是否强制接星火后再补。"
            )
        else:
            raise ValueError(f"未知 LLM_PROVIDER: {config.LLM_PROVIDER}")
        self.provider = provider

    def chat(self, messages, tools=None, tool_choice="auto"):
        """一次对话调用，返回 message 对象（可能含 tool_calls）。"""
        kwargs = {"model": self._model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        resp = self._client.chat.completions.create(**kwargs)
        return resp.choices[0].message