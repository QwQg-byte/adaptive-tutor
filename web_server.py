"""伴学 Agent Demo UI 服务端 —— FastAPI。

跑：python web_server.py  → http://127.0.0.1:8600
把命令行里的"诊断 → 画像 → 路径变短"闭环搬上网页，能演示 / 给学生试用。
依赖：图谱后端(8000)在跑 + .env 有 DEEPSEEK_API_KEY。
"""
import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

import config
import graph_tools
import tutor_agent as ta
from graph_client import GraphClient
from learning_state import (
    GraphUnavailable,
    InvalidLearningContext,
    LearningStateService,
    LearningTargetNotFound,
    RevisionConflict,
)
from llm import LLMClient
from voice_service import (
    ALLOWED_AUDIO_TYPES,
    VoiceConfigurationError,
    VoiceError,
    create_voice_service,
)

logger = logging.getLogger(__name__)
app = FastAPI(title="自适应伴学 Demo")
_client = LLMClient()
_graph = GraphClient()
_learning = LearningStateService(graph=_graph)
_voice_service = None
_voice_configuration_error = None
DIGITAL_HUMAN_VIDEO = Path(__file__).parent / "assets" / "companion-digital-human.mp4"
CHAT_WAITING_VIDEO = (
    Path(__file__).parent / "assets" / "chat-waiting" / "摆手的小熊-optimized-640x360-15fps.mp4"
)
if config.VOICE_ENABLED:
    try:
        _voice_service = create_voice_service(config)
    except VoiceConfigurationError as exc:
        _voice_configuration_error = exc
        logger.error("Voice service disabled; invalid configuration: %s", ", ".join(exc.missing))

# 每个学生一份会话状态（demo 单机足够）
_sessions = {}  # student -> {"messages":[...], "history":[...], "in_diagnostic":bool}
_session_registry_lock = threading.Lock()
_session_locks = {}


def _error(status_code: int, code: str, message: str, **extra):
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, **extra}},
    )


@app.exception_handler(RevisionConflict)
def revision_conflict(_request: Request, exc: RevisionConflict):
    return _error(
        409,
        "revision_conflict",
        str(exc),
        current_revision=exc.current_revision,
    )


@app.exception_handler(LearningTargetNotFound)
def target_not_found(_request: Request, exc: LearningTargetNotFound):
    return _error(404, "target_not_found", str(exc))


@app.exception_handler(InvalidLearningContext)
def invalid_learning_context(_request: Request, exc: InvalidLearningContext):
    return _error(422, "invalid_learning_context", str(exc))


@app.exception_handler(GraphUnavailable)
def graph_unavailable(_request: Request, exc: GraphUnavailable):
    return _error(503, "graph_unavailable", str(exc))


@app.exception_handler(RequestValidationError)
def validation_error(_request: Request, exc: RequestValidationError):
    details = [
        {"location": list(error["loc"]), "message": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return _error(422, "validation_error", "请求参数无效", details=details)


def _student_lock(student):
    with _session_registry_lock:
        return _session_locks.setdefault(student, threading.RLock())


def _session(student):
    with _session_registry_lock:
        if student not in _sessions:
            _sessions[student] = {
                "messages": [{"role": "system", "content": ta.SYSTEM}],
                "history": [],
                "in_diagnostic": False,
            }
        return _sessions[student]


def _unwrap(r):
    if isinstance(r, dict) and "data" in r:
        return r["data"]
    return r


def _steps(plan):
    d = _unwrap(plan)
    if isinstance(d, dict):
        return d.get("path") or d.get("steps") or []
    return d if isinstance(d, list) else []


class ChatIn(BaseModel):
    student: str = "demo_student"
    message: str


class VoiceSpeechIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    request_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )


def _voice_request_id(value: str | None) -> str:
    return value or f"voice-{uuid.uuid4().hex}"


def _voice_error(exc: VoiceError, request_id: str):
    response = _error(exc.status_code, exc.code, str(exc))
    response.headers["X-Request-ID"] = request_id
    response.headers["Cache-Control"] = "no-store"
    return response


def _voice_unavailable(request_id: str):
    if _voice_configuration_error:
        message = "语音服务配置不完整"
    else:
        message = "语音功能未启用"
    response = _error(503, "voice_disabled", message)
    response.headers["X-Request-ID"] = request_id
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/voice/capabilities")
def voice_capabilities():
    enabled = _voice_service is not None
    return {
        "enabled": enabled,
        "provider": config.VOICE_PROVIDER if enabled else None,
        "transcription": enabled,
        "speech": enabled,
        "audio_types": sorted(ALLOWED_AUDIO_TYPES),
        "max_audio_bytes": config.VOICE_MAX_AUDIO_BYTES,
        "max_audio_seconds": config.VOICE_MAX_AUDIO_SECONDS,
        "max_tts_chars": config.VOICE_TTS_MAX_CHARS,
    }


@app.post("/api/voice/transcriptions")
async def voice_transcription(
    audio: Annotated[UploadFile, File()],
    request_id: Annotated[
        str | None,
        Form(
            min_length=1,
            max_length=200,
            pattern=r"^[A-Za-z0-9._:-]+$",
        ),
    ] = None,
):
    current_request_id = _voice_request_id(request_id)
    if _voice_service is None:
        await audio.close()
        return _voice_unavailable(current_request_id)
    try:
        data = await audio.read(config.VOICE_MAX_AUDIO_BYTES + 1)
        text = await _voice_service.transcribe(data, audio.content_type or "")
    except VoiceError as exc:
        return _voice_error(exc, current_request_id)
    finally:
        await audio.close()
    response = JSONResponse(
        content={"text": text, "request_id": current_request_id},
        headers={"X-Request-ID": current_request_id, "Cache-Control": "no-store"},
    )
    return response


@app.post("/api/voice/speech")
async def voice_speech(inp: VoiceSpeechIn):
    current_request_id = _voice_request_id(inp.request_id)
    if _voice_service is None:
        return _voice_unavailable(current_request_id)
    try:
        audio, content_type = await _voice_service.synthesize(inp.text)
    except VoiceError as exc:
        return _voice_error(exc, current_request_id)
    return Response(
        content=audio,
        media_type=content_type,
        headers={"X-Request-ID": current_request_id, "Cache-Control": "no-store"},
    )


@app.post("/api/chat")
def chat(inp: ChatIn):
    """一轮对话：路由→（可能强制）工具→自然语言回复。返回回复+本轮工具+画像。"""
    with _student_lock(inp.student):
        sess = _session(inp.student)
        context = ta.TurnContext(
            student_id=inp.student,
            in_diagnostic=sess["in_diagnostic"],
        )
        forced = ta.route_intent(
            inp.message,
            in_diagnostic=context.in_diagnostic,
        )
        sess["messages"].append({"role": "user", "content": inp.message})
        sess["history"].append({"role": "user", "content": inp.message})
        reply = ta.run_turn(
            _client,
            sess["messages"],
            forced_tool=forced,
            context=context,
        )

        sess["in_diagnostic"] = context.in_diagnostic
        tools = list(context.tool_log)
        sess["history"].append({"role": "assistant", "content": reply, "tools": tools})
        return {
            "reply": reply,
            "routed_to": forced or "auto",
            "tools": tools,
            "profile": graph_tools._learner.profile(inp.student),
            "in_diagnostic": sess["in_diagnostic"],
        }


@app.get("/api/chat/history")
def chat_history(student: str = Query(default="demo_student", max_length=200)):
    """Return display-safe conversation turns for restoring the Tutor UI."""
    with _student_lock(student):
        sess = _session(student)
        return {"student": student, "items": sess["history"][-200:]}


@app.get("/api/profile")
def profile(student: str = "demo_student"):
    return _learning.profile(student)


class PlanIn(BaseModel):
    student: str = "demo_student"
    target: str


@app.post("/api/plan")
def plan(inp: PlanIn):
    """Compatibility route; personalized planning is owned by the learner API."""
    if not config.UNIFIED_LEARNING_STATE:
        prunable = graph_tools._learner.prunable_ids(inp.student)
        mastered = graph_tools._learner.mastered_ids(inp.student)
        base = _steps(_graph.generate_plan(target=inp.target, mastered=[]))
        pruned = _steps(_graph.generate_plan(target=inp.target, mastered=prunable))
        pruned_ids = {step.get("id") for step in pruned}
        return {
            "target": inp.target,
            "baseline_len": len(base),
            "pruned_len": len(pruned),
            "prunable": prunable,
            "mastered": mastered,
            "dropped": [
                {"id": step.get("id"), "name": step.get("name")}
                for step in base
                if step.get("id") not in pruned_ids
            ],
            "steps": pruned,
        }
    return _learning.generate_plan(inp.student, inp.target)


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UnifiedPlanIn(StrictInput):
    target: str = Field(min_length=1, max_length=200)
    difficulty_preference: str = Field(default="balanced", pattern="^(foundation|balanced|challenge)$")
    max_depth: int = Field(default=6, ge=1, le=10)
    questions_per_step: int = Field(default=3, ge=0, le=5)
    expected_revision: int | None = Field(default=None, ge=0)


class KnowledgeStateIn(StrictInput):
    manual_override: str | None = Field(default=None, pattern="^(mastered|learning)$")
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=200)
    node_name: str = Field(default="", max_length=200)


class PlanStepIn(StrictInput):
    status: str = Field(pattern="^(in_progress|completed)$")
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=200)


class AttemptIn(StrictInput):
    question_id: str = Field(min_length=1, max_length=200)
    target_id: str | None = Field(default=None, max_length=200)
    path_node_id: str | None = Field(default=None, max_length=200)
    correct: bool
    source_page: str = Field(pattern="^(tutor|graph)$")
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=200)


class MistakeStateIn(StrictInput):
    status: str = Field(pattern="^resolved$")
    resolution: str = Field(pattern="^manual_review$")
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=200)


class LocalImportIn(StrictInput):
    state: dict
    expected_revision: int | None = Field(default=None, ge=0)
    preview: bool = False


@app.get("/api/learners/{student_id}/state")
def learner_state(student_id: str):
    return _learning.state(student_id)


@app.get("/api/learners/{student_id}/dashboard")
def learner_dashboard(student_id: str):
    return _learning.dashboard(student_id)


@app.post("/api/learners/{student_id}/plans")
def learner_plan(student_id: str, inp: UnifiedPlanIn):
    return _learning.generate_plan(
        student_id,
        inp.target,
        difficulty_preference=inp.difficulty_preference,
        max_depth=inp.max_depth,
        questions_per_step=inp.questions_per_step,
        expected_revision=inp.expected_revision,
    )


@app.patch("/api/learners/{student_id}/knowledge/{node_id}")
def learner_knowledge(student_id: str, node_id: str, inp: KnowledgeStateIn):
    return _learning.set_manual_override(
        student_id,
        node_id,
        inp.manual_override,
        inp.expected_revision,
        inp.idempotency_key,
        node_name=inp.node_name,
    )


@app.put("/api/learners/{student_id}/plans/{target_id}/steps/{node_id}")
def learner_plan_step(student_id: str, target_id: str, node_id: str, inp: PlanStepIn):
    return _learning.set_plan_step(
        student_id,
        target_id,
        node_id,
        inp.status,
        inp.expected_revision,
        inp.idempotency_key,
    )


@app.post("/api/learners/{student_id}/attempts")
def learner_attempt(student_id: str, inp: AttemptIn):
    return _learning.record_attempt(
        student_id,
        inp.question_id,
        inp.correct,
        inp.source_page,
        inp.expected_revision,
        inp.idempotency_key,
        target_id=inp.target_id,
        path_node_id=inp.path_node_id,
    )


@app.get("/api/learners/{student_id}/mistakes")
def learner_mistakes(
    student_id: str,
    status: str | None = Query(default=None, pattern="^(open|resolved)$"),
    target_id: str | None = Query(default=None, max_length=200),
):
    return _learning.mistakes(student_id, status=status, target_id=target_id)


@app.patch("/api/learners/{student_id}/mistakes/{question_id}")
def learner_mistake(student_id: str, question_id: str, inp: MistakeStateIn):
    return _learning.resolve_mistake(
        student_id,
        question_id,
        inp.resolution,
        inp.expected_revision,
        inp.idempotency_key,
    )


@app.post("/api/learners/{student_id}/imports/local-v1")
def learner_import(student_id: str, inp: LocalImportIn):
    return _learning.import_local_v1(
        student_id,
        inp.state,
        expected_revision=inp.expected_revision,
        preview=inp.preview,
    )


@app.get("/companion-digital-human.mp4")
def companion_digital_human_video():
    if not DIGITAL_HUMAN_VIDEO.is_file():
        return Response(status_code=404)
    return FileResponse(
        DIGITAL_HUMAN_VIDEO,
        media_type="video/mp4",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/chat-waiting.mp4")
def chat_waiting_video():
    if not CHAT_WAITING_VIDEO.is_file():
        return Response(status_code=404)
    return FileResponse(
        CHAT_WAITING_VIDEO,
        media_type="video/mp4",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.post("/api/reset")
def reset(student: str = "demo_student"):
    """清掉会话（对话历史+诊断状态）。画像数据留在 DB，不动。"""
    with _student_lock(student):
        with _session_registry_lock:
            _sessions.pop(student, None)
        return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index():
    html = (Path(__file__).parent / "web_ui.html").read_text(encoding="utf-8")
    graph_url = json.dumps(config.GRAPH_FRONTEND_URL).replace("<", "\\u003c")
    return html.replace("__GRAPH_FRONTEND_URL_JSON__", graph_url)


if __name__ == "__main__":
    print("Demo UI: http://127.0.0.1:8600  （需图谱后端 8000 在跑）")
    uvicorn.run(app, host="127.0.0.1", port=8600, log_level="warning")
