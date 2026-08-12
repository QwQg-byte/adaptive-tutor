"""自适应伴学 Agent —— 配置。

路线 B：知识图谱 + 伴学 Agent（暂不接 OJ）。
所有可变项走环境变量 / .env，密钥不写进代码。
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

# 自动加载同目录 .env（若装了 python-dotenv）。环境变量优先于 .env。
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env", override=False)
except ImportError:
    pass


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# ---- 知识图谱后端（地图 + 路径引擎） ----
# 云上部署：http://152.136.151.165/api/v1
# 本地起服务：http://127.0.0.1:8000/api/v1
GRAPH_BASE_URL = _get("GRAPH_BASE_URL", "http://152.136.151.165/api/v1")
GRAPH_TIMEOUT_SECONDS = float(_get("GRAPH_TIMEOUT_SECONDS", "20"))
# Agent 推荐题目时使用的图谱前端入口。题目 ID 和学生 ID 会作为查询参数附加。
GRAPH_FRONTEND_URL = _get("GRAPH_FRONTEND_URL", "http://127.0.0.1:5173")

# ---- LLM（主脑，抽象层）----
# provider: deepseek（现用） | spark（讯飞星火，预留，未实现）
LLM_PROVIDER = _get("LLM_PROVIDER", "deepseek")

DEEPSEEK_BASE_URL = _get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = _get("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_API_KEY = _get("DEEPSEEK_API_KEY", "")

# 讯飞星火（分叉点 B：确认赛题是否强制后再填）
SPARK_BASE_URL = _get("SPARK_BASE_URL", "")
SPARK_MODEL = _get("SPARK_MODEL", "")
SPARK_API_KEY = _get("SPARK_API_KEY", "")

# ---- 讯飞语音（与星火文本模型凭据分开）----
VOICE_ENABLED = _get("VOICE_ENABLED", "false").strip().lower() in {
    "1", "true", "yes", "on"
}
VOICE_PROVIDER = _get("VOICE_PROVIDER", "xfyun").strip().lower()
XFYUN_VOICE_APP_ID = _get("XFYUN_VOICE_APP_ID", "")
XFYUN_VOICE_API_KEY = _get("XFYUN_VOICE_API_KEY", "")
XFYUN_VOICE_API_SECRET = _get("XFYUN_VOICE_API_SECRET", "")
XFYUN_ASR_ENDPOINT = _get("XFYUN_ASR_ENDPOINT", "wss://iat-api.xfyun.cn/v2/iat")
XFYUN_TTS_ENDPOINT = _get("XFYUN_TTS_ENDPOINT", "wss://tts-api.xfyun.cn/v2/tts")
XFYUN_TTS_VOICE = _get("XFYUN_TTS_VOICE", "xiaoyan")
VOICE_FFMPEG_PATH = _get("VOICE_FFMPEG_PATH", "")
VOICE_MAX_AUDIO_BYTES = int(_get("VOICE_MAX_AUDIO_BYTES", "5242880"))
VOICE_MAX_AUDIO_SECONDS = float(_get("VOICE_MAX_AUDIO_SECONDS", "60"))
VOICE_TTS_MAX_CHARS = int(_get("VOICE_TTS_MAX_CHARS", "2000"))
VOICE_CONNECT_TIMEOUT_SECONDS = float(_get("VOICE_CONNECT_TIMEOUT_SECONDS", "10"))
VOICE_REQUEST_TIMEOUT_SECONDS = float(_get("VOICE_REQUEST_TIMEOUT_SECONDS", "45"))
VOICE_AUDIO_DECODE_TIMEOUT_SECONDS = float(
    _get("VOICE_AUDIO_DECODE_TIMEOUT_SECONDS", "15")
)

SESSIONS_DIR = BASE_DIR / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)

# ---- 学习者模型（能力画像 + 长期记忆）----
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
LEARNER_DB = _get("LEARNER_DB", str(DATA_DIR / "learner.db"))
# 掌握度达到该阈值即视为"已掌握"（画像里打 ✓、判断强弱项用）
MASTERY_THRESHOLD = float(_get("MASTERY_THRESHOLD", "0.7"))
# 喂给路径引擎裁剪前置的阈值：比 MASTERY_THRESHOLD 低，让诊断软置信(seed=0.55)
# 的前置也能被跳过——软置信本就是"大概率会"的信号，够格从路径里裁掉，
# 后续真题再确认。两阈值分工：0.7 判"已掌握"给人看，0.5 判"可跳过"给引擎用。
PRUNE_THRESHOLD = float(_get("PRUNE_THRESHOLD", "0.5"))
UNIFIED_LEARNING_STATE = _get("UNIFIED_LEARNING_STATE", "true").strip().lower() in {
    "1", "true", "yes", "on"
}
