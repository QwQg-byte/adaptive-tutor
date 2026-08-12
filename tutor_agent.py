"""自适应伴学 Agent —— 阶段 0 骨架。

复用 multi-agent-mcp 的编排模式：主脑 LLM + function-calling 工具环路。
本阶段只接通"图谱工具"，验证 Agent 能连图谱说话。
后续阶段再叠：学情诊断、脚手架辅导、长期记忆、GraphRAG、Demo UI。

运行：python tutor_agent.py        （建议用项目 .venv）
退出：输入 exit
"""
import json
import sys
from dataclasses import dataclass, field

import graph_tools
from llm import LLMClient

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if not sys.stdin.isatty() and hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")

SYSTEM = (
    "你是一个自适应学习伴学智能体，面向程序设计/算法学科。\n"
    "你的能力：\n"
    "1. 通过知识图谱了解知识点及其前置依赖关系；\n"
    "2. 读取学生能力画像（get_student_profile）：已掌握/薄弱知识点及掌握度；\n"
    "3. 为学生生成个性化学习路径（generate_learning_plan，自动按画像裁剪已掌握前置）；\n"
    "4. 从图谱给某知识点推荐练习题（questions_of_knowledge），并把图谱站内题目简介页推给学生；\n"
    "5. 记录学生每次答题表现（record_result），持续更新画像与长期记忆；\n"
    "6. 读取知识点的图谱教学内容（get_knowledge_detail：概述/基本思想/性质/求解步骤/经典题型/前置）用于讲解与辅导。\n"
    "7. 用 GraphRAG（retrieve_graph_context）检索围绕问题的有界相关子图，基于节点和关系证据回答跨知识点问题。\n"
    "硬性触发规则（先调工具，再回话；一句话里给了目标就别用反问代替动作）：\n"
    "· 学生说出想学的目标（如'我想学动态规划'）→ 第一步就调 generate_learning_plan(target=该主题)，"
    "不要先查画像、不要反问'你想学什么'。裁剪已掌握前置由该工具内部自动完成，无需你先看画像。\n"
    "· 学生报告某题做对/做错（如'递归那题我做对了'）→ 先 search_graph 定位 node_id，再调 record_result 记下。\n"
    "· 学生主动问'我的画像/我学得怎样'→ 调 get_student_profile。仅此场景才需要主动看画像。\n"
    "· 找不到确切知识点时用 search_graph 按关键词查，别猜 node_id。\n"
    "· 学生要求推荐某知识点的题目时，必须先调 questions_of_knowledge 从图谱选一道题；"
    "学生点名具体题目时，先调 search_graph 定位 Question，命中后直接使用该结果的 detail_url，"
    "不要把题目名称当成知识点再次查询。回复只给工具返回的 detail_url"
    "（用普通 URL，方便界面生成可点击链接），绝不直接给码蹄集或其他外部 OJ 链接；"
    "提醒学生可在详情页标记『做对了/做错了』。\n"
    "· 学生要求讲解某知识点（如'讲讲动态规划'）、或做题卡住喊'我不会/没思路/卡住了/给点提示'"
    "→ 先调 get_knowledge_detail 拿到该知识点的真实教学内容，再据此辅导。\n"
    "· 学生询问知识点之间的区别/联系/关系、为什么需要某个前置、依赖链或适用场景"
    "→ 先调 retrieve_graph_context(query=学生原始问题, topics=识别出的知识点名称)，只依据返回的 nodes/edges 作答；"
    "回答中点明所依据的知识点名称，图中没有证据就明确说证据不足。\n"
    "画像为空只说明是新学生，绝不因此改变上面的规则或转入寒暄引导——目标已给就照样规划。\n"
    "【脚手架辅导原则】辅导要循序渐进地『给脚手架』，不是一次把答案倒完：\n"
    "① 先调 get_knowledge_detail 接地，只依据返回的真实内容讲，绝不凭空编概念或步骤；\n"
    "② 分层给提示——先点方向（这题属于哪类、该往哪想），再给关键概念/性质，"
    "最后才谈具体求解步骤；每层之间留出让学生自己想的空间，可反问'你觉得状态该怎么定义？'；\n"
    "③ 学生仍不懂再往下深入一层，别一步跳到完整题解；讲题目思路时给分析框架而非直接写出答案。\n"
    "用中文交流。需要数据一律调工具，不要凭空编造知识点、题目或掌握度。"
)

MAX_TOOL_HOPS = 6

# ---- 意图预路由：治 DeepSeek 在 auto 下偷懒不调工具的毛病 ----
# 命中明确意图时，第一跳强制它调对应工具（参数仍由模型抽取）；其余交给 auto。
_LEARN_KW = ("想学", "我要学", "教我", "带我学", "怎么学", "规划", "学习路径", "路线", "学一下", "学下")
_RESULT_KW = ("做对", "答对", "做错", "答错", "做出来了", "没做出来", "过了这题", "这题对", "这题错",
              "对了", "错了", "全对", "做完了", "AC了", "通过了")
_PROFILE_KW = ("画像", "学得怎", "我的水平", "掌握了", "掌握程度", "我会哪些", "我会啥", "我的进度",
               "薄弱", "强项", "哪里弱", "学情")
_DIAGNOSE_KW = ("摸底", "诊断", "测测", "测一下", "测测我", "评估一下", "摸个底", "测试我",
                "看看我会多少", "先测", "做个测试")
# 脚手架辅导触发：讲解某知识点，或做题卡住求提示 → 先接地再分层引导
_TUTOR_KW = ("讲讲", "讲一下", "讲解", "解释", "说说", "什么是", "介绍一下", "带我理解",
             "我不会", "不会做", "没思路", "没头绪", "卡住", "卡住了", "给点提示", "提示一下",
             "怎么做", "怎么想", "不懂", "看不懂", "教教我这题")
# 需要多个节点或关系证据的问题优先走 GraphRAG；顺序必须在单点讲解之前。
_GRAPH_RAG_KW = ("区别", "差异", "对比", "比较", "联系", "关系", "关联", "为什么", "为何",
                 "前置", "依赖", "知识体系", "相关知识", "适用场景", "什么时候用")
_QUESTION_RECOMMEND_KW = ("推荐", "来一道", "来一题", "找一道", "找一题", "给我一道", "给我一题")

@dataclass
class TurnContext:
    """Request-local learner context for one Agent turn."""

    student_id: str
    in_diagnostic: bool = False
    tool_log: list[str] = field(default_factory=list)

    def record_tool(self, name: str) -> None:
        self.tool_log.append(name)
        if name == "start_diagnostic":
            self.in_diagnostic = True
        elif name == "diagnose_answer":
            self.in_diagnostic = False


def route_intent(text: str, *, in_diagnostic: bool = False):
    """返回 tool_name | None。None 表示交给 auto。"""
    t = text.strip()
    # 明确要求摸底 → 开诊断
    if any(k in t for k in _DIAGNOSE_KW):
        return "start_diagnostic"
    # 对错上报：诊断进行中走 diagnose_answer，否则走 record_result
    if any(k in t for k in _RESULT_KW):
        return "diagnose_answer" if in_diagnostic else "record_result"
    if any(k in t for k in _PROFILE_KW):
        return "get_student_profile"
    if any(k in t for k in _GRAPH_RAG_KW):
        return "retrieve_graph_context"
    # 辅导/讲解在规划之前判：'讲讲X''这题不会'先接地，别被'学'类词抢走
    if any(k in t for k in _TUTOR_KW):
        return "get_knowledge_detail"
    if any(k in t for k in _LEARN_KW):
        return "generate_learning_plan"
    return None


def _wants_question_recommendation(messages) -> bool:
    user_text = next(
        (str(message.get("content") or "") for message in reversed(messages)
         if message.get("role") == "user"),
        "",
    )
    return "题" in user_text and any(keyword in user_text for keyword in _QUESTION_RECOMMEND_KW)


def _question_candidates(tool_result: str) -> list[dict]:
    try:
        payload = json.loads(tool_result)
    except (TypeError, json.JSONDecodeError):
        return []
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not isinstance(data, list):
        return []
    return [
        item for item in data
        if isinstance(item, dict) and item.get("detail_url")
    ]


def _ensure_question_detail_link(reply: str, candidates: list[dict]) -> str:
    if not candidates or any(item["detail_url"] in reply for item in candidates):
        return reply
    selected = next(
        (
            item for item in candidates
            if (item.get("name") and str(item["name"]) in reply)
            or (item.get("id") and str(item["id"]) in reply)
        ),
        candidates[0],
    )
    return (
        f"{reply.rstrip()}\n\n题目简介页：{selected['detail_url']}\n"
        "打开后可以标记“做对了”或“做错了”。"
    )


def run_turn(client, messages, forced_tool=None, *, context: TurnContext):
    """跑一轮：允许 LLM 连续调用若干次工具，直到给出自然语言回复。

    forced_tool 只作用于第一跳（强制模型调该工具），之后恢复 auto，
    让它拿到工具结果后能正常收尾成自然语言。
    """
    wants_question = _wants_question_recommendation(messages)
    question_candidates = []
    for hop in range(MAX_TOOL_HOPS):
        if hop == 0 and forced_tool:
            choice = {"type": "function", "function": {"name": forced_tool}}
        else:
            choice = "auto"
        msg = client.chat(messages, tools=graph_tools.TOOLS, tool_choice=choice)
        messages.append(msg.model_dump(exclude_none=True))
        if not msg.tool_calls:
            reply = msg.content or ""
            if wants_question:
                reply = _ensure_question_detail_link(reply, question_candidates)
            return reply
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            context.record_tool(call.function.name)
            result = graph_tools.dispatch(
                call.function.name,
                args,
                student_id=context.student_id,
            )
            if wants_question and call.function.name in {"search_graph", "questions_of_knowledge"}:
                question_candidates.extend(_question_candidates(result))
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            })
    return "（工具调用次数超上限，先停在这里。）"


def main():
    client = LLMClient()
    try:
        student = input("学生 ID（回车用 demo_student）：").strip() or "demo_student"
    except (EOFError, KeyboardInterrupt):
        student = "demo_student"
    print(f"伴学 Agent 已启动（LLM={client.provider}，学生={student}）。输入 exit 退出。\n")
    messages = [{"role": "system", "content": SYSTEM}]
    in_diagnostic = False
    while True:
        try:
            user = input("你：").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user.lower() in {"exit", "quit"}:
            break
        if not user:
            continue
        messages.append({"role": "user", "content": user})
        context = TurnContext(student, in_diagnostic=in_diagnostic)
        reply = run_turn(
            client,
            messages,
            forced_tool=route_intent(user, in_diagnostic=in_diagnostic),
            context=context,
        )
        in_diagnostic = context.in_diagnostic
        print(f"\n伴学 Agent：{reply}\n")


if __name__ == "__main__":
    main()
