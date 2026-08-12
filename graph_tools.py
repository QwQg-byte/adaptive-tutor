# -*- coding: utf-8 -*-
"""图谱工具 —— OpenAI function-calling schema + dispatch。

沿用 multi-agent-mcp 的工具模式：schema 挂进 TOOLS，
Agent 决定何时调用，dispatch() 执行并把结果回灌对话。
"""
import json
from urllib.parse import urlencode

import config
import graph_rag
from graph_client import GraphClient
from learner_model import LearnerModel

_graph = GraphClient()
_learner = LearnerModel()

def _unwrap(r):
    """图谱统一响应 {success,message,data} → data；否则原样。"""
    if isinstance(r, dict) and "data" in r and set(r.keys()) <= {"success", "message", "data", "code"}:
        return r["data"]
    return r


def _question_detail_url(question_id: str, student_id: str) -> str:
    """Build the graph UI entry for a question in the supplied learner context."""
    query = urlencode({"id": str(question_id), "student": student_id})
    return f"{config.GRAPH_FRONTEND_URL.rstrip('/')}/questions?{query}"


def _prepare_question(raw: dict, student_id: str) -> dict:
    question = dict(raw)
    for key in ("url", "source_url", "external_url", "oj_url", "link"):
        question.pop(key, None)
    question_id = question.get("id") or question.get("question_id")
    if question_id:
        question["detail_url"] = _question_detail_url(question_id, student_id)
    return question


def _question_presentation_instruction() -> str:
    return (
        "推荐时只选择一道题，并只向学生提供该题的 detail_url；"
        "这是可查看题目简介并记录做对/做错的图谱站内页面。不要提供外部 OJ 链接。"
    )


def _replace_response_data(response, data: list, *, include_instruction: bool):
    result = dict(response) if isinstance(response, dict) else {}
    result["data"] = data
    if include_instruction:
        result["presentation_instruction"] = _question_presentation_instruction()
    return result


def _questions_for_tutor(response, student_id: str):
    """Expose graph detail pages to the LLM without leaking direct OJ links."""
    questions = _unwrap(response)
    if not isinstance(questions, list):
        return response

    prepared = [
        _prepare_question(raw, student_id) for raw in questions if isinstance(raw, dict)
    ]
    return _replace_response_data(response, prepared, include_instruction=True)


def _search_results_for_tutor(response, student_id: str):
    """Add graph detail URLs when a general graph search returns question nodes."""
    hits = _unwrap(response)
    if not isinstance(hits, list):
        return response

    found_question = False
    prepared = []
    for raw in hits:
        if not isinstance(raw, dict):
            prepared.append(raw)
            continue
        if raw.get("label") == "Question" or raw.get("type") == "Question":
            prepared.append(_prepare_question(raw, student_id))
            found_question = True
        else:
            prepared.append(raw)
    return _replace_response_data(
        response,
        prepared,
        include_instruction=found_question,
    )


def resolve_knowledge_node(name_or_kw: str):
    """把知识点名字/关键词解析成规范知识节点 {id: NODE_xxx, name}。

    规划路径与画像裁剪都以 NODE_xxx 为准；搜索结果里章节(CHAP)、题目(Question)
    要滤掉，只取 label==KnowledgeNode 的最高分命中。找不到返回 None。
    """
    if not name_or_kw:
        return None
    hits = _unwrap(_graph.search(keyword=name_or_kw)) or []
    knodes = [h for h in hits if isinstance(h, dict) and h.get("label") == "KnowledgeNode"]
    if not knodes:
        return None
    best = knodes[0]  # 搜索已按 search_score 降序
    return {"id": best.get("id"), "name": best.get("name")}


def knowledge_detail(name_or_kw: str) -> dict:
    """抽取一个知识点的教学内容，作为脚手架辅导的『接地素材』。

    只回图谱里真实存在的字段（overview/elaboration/applications/learning_tips/tags）
    加直接前置名——让 LLM 依据真实内容给分层提示，不凭空编。
    这也是阶段5 GraphRAG 的检索原语。找不到返回 {"found": False}。
    """
    hits = _unwrap(_graph.search(keyword=name_or_kw)) or []
    knodes = [h for h in hits if isinstance(h, dict) and h.get("label") == "KnowledgeNode"]
    if not knodes:
        return {"found": False, "query": name_or_kw}
    n = knodes[0]
    try:
        detail = _unwrap(_graph.knowledge_point_detail(n.get("id"))) or {}
        canonical = detail.get("knowledge_point") if isinstance(detail, dict) else None
        if isinstance(canonical, dict):
            n = {**n, **canonical, "id": canonical.get("id") or n.get("id")}
    except Exception:
        # Older graph backends may not expose the detail endpoint. Search
        # results already contain node properties, so they remain a valid fallback.
        pass
    prereqs = []
    try:
        dep = _unwrap(_graph.dependencies(n.get("name", ""))) or {}
        prereqs = [p.get("name") for p in (dep.get("prerequisites") or [])
                   if isinstance(p, dict) and p.get("name")]
    except Exception:
        pass
    return {
        "found": True,
        "id": n.get("id"),
        "name": n.get("name"),
        "overview": n.get("overview") or "",
        "elaboration": n.get("elaboration") or "",     # 基本思想/性质/求解步骤
        "applications": n.get("applications") or "",   # 经典题型
        "learning_tips": n.get("learning_tips") or "",
        "tags": n.get("tags") or [],
        "prerequisites": prereqs[:12],
    }

GENERATE_PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_learning_plan",
        "description": (
            "基于知识图谱为学生生成通往目标知识点的个性化学习路径，"
            "会根据已掌握知识点自动裁剪前置。学生想学某个主题、"
            "或诊断出薄弱点需要规划下一步时调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "目标知识点名称或业务ID（如 NODE_358 或 '动态规划'）"},
                "mastered": {"type": "array", "items": {"type": "string"},
                             "description": "学生已掌握的知识点ID列表，用于裁剪"},
                "difficulty_preference": {"type": "string", "enum": ["foundation", "balanced", "challenge"],
                                          "description": "训练强度：基础/均衡/挑战"},
            },
            "required": ["target"],
            "additionalProperties": False,
        },
    },
}

LIST_KP_TOOL = {
    "type": "function",
    "function": {
        "name": "list_knowledge_points",
        "description": "列出知识图谱里的知识点，用于了解图谱覆盖范围或给学生选主题。",
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "返回数量上限"}},
            "additionalProperties": False,
        },
    },
}

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_graph",
        "description": "按关键词在知识图谱里搜索知识点或题目节点。",
        "parameters": {
            "type": "object",
            "properties": {"keyword": {"type": "string", "description": "搜索关键词"}},
            "required": ["keyword"],
            "additionalProperties": False,
        },
    },
}

QUESTIONS_OF_KP_TOOL = {
    "type": "function",
    "function": {
        "name": "questions_of_knowledge",
        "description": (
            "从知识图谱中取某个知识点下挂的练习题（用于给学生推题）。"
            "返回的 detail_url 是图谱站内题目简介页，已绑定当前学生；"
            "推荐时只能给学生这个链接，不能给外部 OJ/码蹄集链接。"
        ),
        "parameters": {
            "type": "object",
            "properties": {"knowledge_id": {"type": "string", "description": "知识点业务ID或名称"}},
            "required": ["knowledge_id"],
            "additionalProperties": False,
        },
    },
}

GET_PROFILE_TOOL = {
    "type": "function",
    "function": {
        "name": "get_student_profile",
        "description": (
            "读取当前学生的能力画像：已掌握的知识点、薄弱知识点及各自掌握度。"
            "规划路径或决定辅导重点前先看画像，做到因材施教。"
        ),
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
}

RECORD_RESULT_TOOL = {
    "type": "function",
    "function": {
        "name": "record_result",
        "description": (
            "记录学生在某知识点上的一次表现（诊断题或练习题的对错），"
            "用于更新能力画像和长期记忆。学生答完一题后调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "node_name": {"type": "string", "description": "知识点名称或关键词，如 递归、动态规划。会自动解析成图谱节点。"},
                "node_id": {"type": "string", "description": "可选。知道规范ID(NODE_xxx)时才填，否则留空由 node_name 解析。"},
                "correct": {"type": "boolean", "description": "本次是否答对"},
                "kind": {"type": "string", "enum": ["diagnose", "practice"],
                         "description": "来源：诊断题还是练习题"},
            },
            "required": ["node_name", "correct"],
            "additionalProperties": False,
        },
    },
}

DIAGNOSE_ANSWER_TOOL = {
    "type": "function",
    "function": {
        "name": "diagnose_answer",
        "description": (
            "记录一道『诊断题』的对错，并按前置边传播画像。"
            "与 record_result 的区别：诊断题答对时会顺带把该知识点的直接前置"
            "软置信到一个较高起点（推断学生大概率也会前置），从而快速建立画像、"
            "让后续学习路径立刻变短。学情诊断阶段学生每答一道摸底题就调这个。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "node_name": {"type": "string", "description": "被诊断的知识点名称/关键词，如 递归算法设计"},
                "correct": {"type": "boolean", "description": "本次诊断题是否答对"},
            },
            "required": ["node_name", "correct"],
            "additionalProperties": False,
        },
    },
}

GET_KNOWLEDGE_DETAIL_TOOL = {
    "type": "function",
    "function": {
        "name": "get_knowledge_detail",
        "description": (
            "读取某知识点在图谱里的教学内容：概述、基本思想/性质/求解步骤(elaboration)、"
            "经典题型(applications)、学习建议、直接前置。"
            "学生要求讲解某知识点、或做题卡住需要提示时，先调本工具拿到真实内容，"
            "再据此给分层引导提示——绝不凭空编造概念或步骤。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "node_name": {"type": "string", "description": "知识点名称或关键词，如 动态规划、二分查找"},
            },
            "required": ["node_name"],
            "additionalProperties": False,
        },
    },
}

GRAPH_RAG_TOOL = {
    "type": "function",
    "function": {
        "name": "retrieve_graph_context",
        "description": (
            "围绕学生的问题检索知识图谱证据：定位最多 3 个核心知识点，扩展直接前置、"
            "后继和语义关系，并附上真实教学内容及学生掌握状态。适合回答知识点之间的"
            "区别/联系、为什么需要某前置、适用场景和知识体系问题。拿到证据后只依据"
            "nodes/edges 回答；证据不足要明确说明。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "学生的原始问题，保留涉及的所有知识点"},
                "topics": {"type": "array", "items": {"type": "string"}, "maxItems": 3,
                           "description": "从问题中识别出的核心知识点名称，能识别时填写，最多 3 个"},
                "max_nodes": {"type": "integer", "minimum": 3, "maximum": 12,
                              "description": "证据包最多包含的节点数，默认 8"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

START_DIAGNOSTIC_TOOL = {
    "type": "function",
    "function": {
        "name": "start_diagnostic",
        "description": (
            "开始/继续一轮学情诊断：系统自动挑一个靠下游的代表知识点并给出一道摸底题。"
            "学生想'摸底/测测我的水平/评估一下'，或画像还很空需要快速建立时调用。"
            "拿到题后把题目原样呈现给学生作答，学生答完再调 diagnose_answer 记录。"
        ),
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
}

TOOLS = [GENERATE_PLAN_TOOL, LIST_KP_TOOL, SEARCH_TOOL, QUESTIONS_OF_KP_TOOL,
         GET_PROFILE_TOOL, RECORD_RESULT_TOOL, DIAGNOSE_ANSWER_TOOL, START_DIAGNOSTIC_TOOL,
         GET_KNOWLEDGE_DETAIL_TOOL, GRAPH_RAG_TOOL]


def dispatch(name: str, args: dict, *, student_id: str) -> str:
    """执行一个工具调用，返回 JSON 字符串（回灌给 LLM）。"""
    try:
        if name == "generate_learning_plan":
            # 用画像里『可裁剪』节点(含诊断软置信前置)裁前置；LLM 显式传入的 mastered 作为补充
            mastered = list(
                set(_learner.prunable_ids(student_id)) | set(args.get("mastered", []))
            )
            result = _graph.generate_plan(
                target=args["target"],
                mastered=mastered,
                difficulty_preference=args.get("difficulty_preference", "balanced"),
            )
        elif name == "get_student_profile":
            result = _learner.profile(student_id)
        elif name == "record_result":
            node_id = args.get("node_id", "")
            node_name = args.get("node_name", "")
            # ID 非规范(NODE_xxx)或缺失 → 用名字/关键词解析成规范节点
            if not node_id.startswith("NODE_"):
                node = resolve_knowledge_node(node_id or node_name)
                if not node:
                    result = {"ok": False, "error": f"无法在图谱中定位知识点：{node_name or node_id}"}
                    return json.dumps(result, ensure_ascii=False)
                node_id, node_name = node["id"], node["name"]
            mastery = _learner.record(
                student_id=student_id,
                node_id=node_id,
                node_name=node_name,
                correct=bool(args["correct"]),
                kind=args.get("kind", "practice"),
            )
            result = {"ok": True, "node_id": node_id, "node_name": node_name,
                      "new_mastery": round(mastery, 3)}
        elif name == "start_diagnostic":
            import diagnose  # 延迟导入：diagnose 依赖本模块，避免循环
            result = diagnose.start(student_id)
        elif name == "diagnose_answer":
            node = resolve_knowledge_node(args["node_name"])
            if not node:
                return json.dumps({"ok": False, "error": f"无法定位知识点：{args['node_name']}"},
                                  ensure_ascii=False)
            import diagnose  # 延迟导入：diagnose 依赖本模块，避免循环
            result = diagnose.apply_diagnostic_answer(
                student_id, node["id"], node["name"], bool(args["correct"])
            )
        elif name == "list_knowledge_points":
            result = _graph.list_knowledge_points(limit=args.get("limit", 50))
        elif name == "search_graph":
            result = _search_results_for_tutor(
                _graph.search(keyword=args["keyword"]), student_id
            )
        elif name == "questions_of_knowledge":
            result = _questions_for_tutor(
                _graph.questions_of_knowledge(knowledge_id=args["knowledge_id"]),
                student_id,
            )
        elif name == "get_knowledge_detail":
            result = knowledge_detail(args["node_name"])
        elif name == "retrieve_graph_context":
            profile = _learner.profile(student_id)
            mastery = {n["node_id"]: n["mastery"] for n in profile.get("nodes", [])}
            result = graph_rag.retrieve(
                query=args["query"],
                graph=_graph,
                mastery_by_id=mastery,
                max_nodes=args.get("max_nodes", graph_rag.DEFAULT_MAX_NODES),
                topics=args.get("topics"),
            )
        else:
            return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001 — 工具错误回灌给 LLM 自行处理
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
