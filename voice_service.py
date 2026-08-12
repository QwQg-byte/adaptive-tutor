"""XFYUN voice provider and application-level ASR/TTS service."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from websockets.asyncio.client import connect

DEFAULT_ASR_ENDPOINT = "wss://iat-api.xfyun.cn/v2/iat"
DEFAULT_TTS_ENDPOINT = "wss://tts-api.xfyun.cn/v2/tts"
ASR_CHUNK_BYTES = 1280
ASR_FRAME_INTERVAL_SECONDS = 0.04
PCM_SAMPLE_RATE = 16000
PCM_BYTES_PER_SECOND = PCM_SAMPLE_RATE * 2
MAX_XFYUN_TTS_UTF8_BYTES = 8000

ALLOWED_AUDIO_TYPES = frozenset(
    {
        "audio/m4a",
        "audio/ogg",
        "audio/mp4",
        "audio/wav",
        "audio/wave",
        "audio/x-wav",
        "audio/x-m4a",
        "audio/webm",
    }
)


class VoiceError(RuntimeError):
    code = "voice_error"
    status_code = 500


class VoiceConfigurationError(VoiceError):
    code = "voice_disabled"
    status_code = 503

    def __init__(self, missing: list[str] | tuple[str, ...]):
        self.missing = tuple(missing)
        super().__init__("语音服务配置不完整：" + ", ".join(self.missing))


class VoiceUnsupportedMediaType(VoiceError):
    code = "voice_unsupported_media_type"
    status_code = 415


class VoiceAudioTooLarge(VoiceError):
    code = "voice_audio_too_large"
    status_code = 413


class VoiceAudioInvalid(VoiceError):
    code = "voice_audio_invalid"
    status_code = 422


class VoiceAudioTooLong(VoiceError):
    code = "voice_audio_too_long"
    status_code = 422


class VoiceTextInvalid(VoiceError):
    code = "voice_text_invalid"
    status_code = 422


class VoiceTextTooLong(VoiceError):
    code = "voice_text_too_long"
    status_code = 422


class VoiceProviderTimeout(VoiceError):
    code = "voice_provider_timeout"
    status_code = 504


class VoiceProviderUnavailable(VoiceError):
    code = "voice_provider_unavailable"
    status_code = 503


@dataclass(frozen=True)
class VoiceCredentials:
    app_id: str
    api_key: str
    api_secret: str

    @classmethod
    def from_environment(cls) -> VoiceCredentials:
        values = {
            "XFYUN_VOICE_APP_ID": os.environ.get("XFYUN_VOICE_APP_ID", "").strip(),
            "XFYUN_VOICE_API_KEY": os.environ.get("XFYUN_VOICE_API_KEY", "").strip(),
            "XFYUN_VOICE_API_SECRET": os.environ.get("XFYUN_VOICE_API_SECRET", "").strip(),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise VoiceConfigurationError(missing)
        return cls(*values.values())


@dataclass(frozen=True)
class PcmAudio:
    data: bytes
    sample_rate: int
    duration_seconds: float


def authorization_url(
    endpoint: str,
    api_key: str,
    api_secret: str,
    *,
    now: datetime | None = None,
) -> str:
    """Build an XFYUN HMAC-SHA256 WebSocket URL without logging it."""
    parsed = urlsplit(endpoint)
    if parsed.scheme != "wss" or not parsed.hostname or not parsed.path:
        raise VoiceConfigurationError(["XFYUN endpoint must be an absolute wss:// URL"])

    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    date = format_datetime(moment.astimezone(timezone.utc), usegmt=True)
    host = parsed.netloc
    request_line = f"GET {parsed.path} HTTP/1.1"
    signature_origin = f"host: {host}\ndate: {date}\n{request_line}"
    digest = hmac.new(
        api_secret.encode("utf-8"),
        signature_origin.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    signature = base64.b64encode(digest).decode("ascii")
    authorization_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    authorization = base64.b64encode(
        authorization_origin.encode("utf-8")
    ).decode("ascii")
    existing_query = parse_qs(parsed.query, keep_blank_values=True)
    existing_query.update(
        {"authorization": [authorization], "date": [date], "host": [host]}
    )
    query = urlencode(existing_query, doseq=True)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def asr_frame(
    credentials: VoiceCredentials,
    audio: bytes,
    sample_rate: int,
    status: int,
) -> dict:
    payload: dict = {
        "data": {
            "status": status,
            "format": f"audio/L16;rate={sample_rate}",
            "encoding": "raw",
            "audio": base64.b64encode(audio).decode("ascii"),
        }
    }
    if status == 0:
        payload["common"] = {"app_id": credentials.app_id}
        payload["business"] = {
            "language": "zh_cn",
            "domain": "iat",
            "accent": "mandarin",
        }
    return payload


def tts_request(credentials: VoiceCredentials, text: str, voice: str) -> dict:
    encoded = text.encode("utf-8")
    if not encoded:
        raise VoiceTextInvalid("合成文本不能为空")
    if len(encoded) >= MAX_XFYUN_TTS_UTF8_BYTES:
        raise VoiceTextTooLong("合成文本必须少于 8000 个 UTF-8 字节")
    return {
        "common": {"app_id": credentials.app_id},
        "business": {
            "aue": "lame",
            "sfl": 1,
            "auf": "audio/L16;rate=16000",
            "vcn": voice,
            "tte": "utf8",
        },
        "data": {
            "status": 2,
            "text": base64.b64encode(encoded).decode("ascii"),
        },
    }


def _provider_error(payload: dict, operation: str) -> VoiceProviderUnavailable | None:
    code = payload.get("code", 0)
    if code == 0:
        return None
    sid = str(payload.get("sid") or "")
    suffix = f"，sid={sid}" if sid else ""
    return VoiceProviderUnavailable(f"讯飞{operation}服务返回错误 code={code}{suffix}")


def _asr_text(payload: dict) -> str:
    result = (payload.get("data") or {}).get("result") or {}
    words = []
    for word_segment in result.get("ws") or []:
        candidates = word_segment.get("cw") or []
        if candidates:
            words.append(str(candidates[0].get("w") or ""))
    return "".join(words)


class XfyunVoiceProvider:
    def __init__(
        self,
        credentials: VoiceCredentials,
        *,
        asr_endpoint: str = DEFAULT_ASR_ENDPOINT,
        tts_endpoint: str = DEFAULT_TTS_ENDPOINT,
        voice: str = "xiaoyan",
        connect_timeout_seconds: float = 10,
        request_timeout_seconds: float = 45,
    ):
        self.credentials = credentials
        self.asr_endpoint = asr_endpoint
        self.tts_endpoint = tts_endpoint
        self.voice = voice
        self.connect_timeout_seconds = connect_timeout_seconds
        self.request_timeout_seconds = request_timeout_seconds

    async def _send_asr(self, websocket, audio: PcmAudio) -> None:
        offset = 0
        first = True
        while offset < len(audio.data):
            chunk = audio.data[offset : offset + ASR_CHUNK_BYTES]
            offset += len(chunk)
            last = offset >= len(audio.data)
            status = 0 if first else (2 if last else 1)
            await websocket.send(
                json.dumps(
                    asr_frame(self.credentials, chunk, audio.sample_rate, status),
                    ensure_ascii=False,
                )
            )
            first = False
            if status != 2:
                await asyncio.sleep(ASR_FRAME_INTERVAL_SECONDS)

        if len(audio.data) <= ASR_CHUNK_BYTES:
            await websocket.send(
                json.dumps(
                    asr_frame(self.credentials, b"", audio.sample_rate, 2),
                    ensure_ascii=False,
                )
            )

    @staticmethod
    async def _receive_asr(websocket) -> str:
        segments = []
        async for message in websocket:
            try:
                payload = json.loads(message)
            except (TypeError, json.JSONDecodeError) as exc:
                raise VoiceProviderUnavailable("讯飞语音听写返回了无效响应") from exc
            error = _provider_error(payload, "语音听写")
            if error:
                raise error
            text = _asr_text(payload)
            if text:
                segments.append(text)
            data = payload.get("data") or {}
            result = data.get("result") or {}
            if data.get("status") == 2 or result.get("ls") is True:
                break
        return "".join(segments).strip()

    async def transcribe(self, audio: PcmAudio) -> str:
        url = authorization_url(
            self.asr_endpoint,
            self.credentials.api_key,
            self.credentials.api_secret,
        )

        async def run_request() -> str:
            async with connect(
                url,
                open_timeout=self.connect_timeout_seconds,
            ) as websocket:
                receiver = asyncio.create_task(self._receive_asr(websocket))
                try:
                    await self._send_asr(websocket, audio)
                    return await receiver
                except BaseException:
                    receiver.cancel()
                    raise

        try:
            text = await asyncio.wait_for(
                run_request(), timeout=self.request_timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            raise VoiceProviderTimeout("讯飞语音听写响应超时") from exc
        except VoiceError:
            raise
        except Exception as exc:
            raise VoiceProviderUnavailable("讯飞语音听写服务暂时不可用") from exc
        if not text:
            raise VoiceAudioInvalid("未识别到可用文字，请重新录音")
        return text

    async def synthesize(self, text: str) -> bytes:
        url = authorization_url(
            self.tts_endpoint,
            self.credentials.api_key,
            self.credentials.api_secret,
        )
        request = tts_request(self.credentials, text, self.voice)
        chunks = []

        async def run_request() -> None:
            async with connect(
                url,
                open_timeout=self.connect_timeout_seconds,
            ) as websocket:
                await websocket.send(json.dumps(request, ensure_ascii=False))
                async for message in websocket:
                    try:
                        payload = json.loads(message)
                    except (TypeError, json.JSONDecodeError) as exc:
                        raise VoiceProviderUnavailable(
                            "讯飞语音合成返回了无效响应"
                        ) from exc
                    error = _provider_error(payload, "语音合成")
                    if error:
                        raise error
                    data = payload.get("data") or {}
                    encoded_audio = data.get("audio")
                    if encoded_audio:
                        try:
                            chunks.append(
                                base64.b64decode(encoded_audio, validate=True)
                            )
                        except (ValueError, TypeError) as exc:
                            raise VoiceProviderUnavailable(
                                "讯飞语音合成返回了无效音频"
                            ) from exc
                    if data.get("status") == 2:
                        break

        try:
            await asyncio.wait_for(
                run_request(), timeout=self.request_timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            raise VoiceProviderTimeout("讯飞语音合成响应超时") from exc
        except VoiceError:
            raise
        except Exception as exc:
            raise VoiceProviderUnavailable("讯飞语音合成服务暂时不可用") from exc
        result = b"".join(chunks)
        if not result:
            raise VoiceProviderUnavailable("讯飞语音合成未返回音频")
        return result


class FfmpegAudioConverter:
    def __init__(
        self,
        executable: str,
        *,
        max_audio_seconds: float,
        timeout_seconds: float = 15,
    ):
        self.executable = executable
        self.max_audio_seconds = max_audio_seconds
        self.timeout_seconds = timeout_seconds

    @classmethod
    def discover(
        cls,
        configured_path: str,
        *,
        max_audio_seconds: float,
        timeout_seconds: float = 15,
    ) -> FfmpegAudioConverter:
        executable = configured_path.strip()
        if not executable:
            try:
                import imageio_ffmpeg

                executable = imageio_ffmpeg.get_ffmpeg_exe()
            except (ImportError, RuntimeError) as exc:
                raise VoiceConfigurationError(
                    ["VOICE_FFMPEG_PATH or imageio-ffmpeg"]
                ) from exc
        if not Path(executable).is_file():
            raise VoiceConfigurationError(["VOICE_FFMPEG_PATH"])
        return cls(
            executable,
            max_audio_seconds=max_audio_seconds,
            timeout_seconds=timeout_seconds,
        )

    def convert(self, audio: bytes) -> PcmAudio:
        decode_limit = self.max_audio_seconds + 0.25
        command = [
            self.executable,
            "-v",
            "error",
            "-nostdin",
            "-i",
            "pipe:0",
            "-t",
            f"{decode_limit:.3f}",
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(PCM_SAMPLE_RATE),
            "-c:a",
            "pcm_s16le",
            "-f",
            "s16le",
            "pipe:1",
        ]
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            completed = subprocess.run(
                command,
                input=audio,
                capture_output=True,
                check=False,
                timeout=self.timeout_seconds,
                creationflags=creation_flags,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise VoiceAudioInvalid("音频解码失败，请重新录音") from exc
        if completed.returncode != 0 or not completed.stdout:
            raise VoiceAudioInvalid("音频为空或格式无效")
        duration = len(completed.stdout) / PCM_BYTES_PER_SECOND
        if duration > self.max_audio_seconds:
            raise VoiceAudioTooLong(
                f"录音超过 {self.max_audio_seconds:g} 秒，请缩短后重试"
            )
        return PcmAudio(
            data=completed.stdout,
            sample_rate=PCM_SAMPLE_RATE,
            duration_seconds=duration,
        )


_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(https?://[^)]+\)", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_MARKDOWN_MARK_RE = re.compile(r"(?m)^\s{0,3}(?:#{1,6}|[-*+]\s)|[*_~`]+")


def normalize_speech_text(text: str) -> str:
    """Remove presentation syntax while preserving the page's original reply."""
    spoken = _CODE_BLOCK_RE.sub("代码段已显示在页面。", text)
    spoken = _MARKDOWN_LINK_RE.sub(r"\1，相关题目链接已显示在页面。", spoken)
    spoken = _URL_RE.sub("相关题目链接已显示在页面。", spoken)
    spoken = _MARKDOWN_MARK_RE.sub("", spoken)
    return re.sub(r"\s+", " ", spoken).strip()


class VoiceService:
    def __init__(
        self,
        provider: XfyunVoiceProvider,
        converter: FfmpegAudioConverter,
        *,
        max_audio_bytes: int,
        max_tts_chars: int,
    ):
        self.provider = provider
        self.converter = converter
        self.max_audio_bytes = max_audio_bytes
        self.max_audio_seconds = converter.max_audio_seconds
        self.max_tts_chars = max_tts_chars

    async def transcribe(self, audio: bytes, content_type: str) -> str:
        media_type = (content_type or "").split(";", 1)[0].strip().lower()
        if media_type not in ALLOWED_AUDIO_TYPES:
            raise VoiceUnsupportedMediaType("不支持该录音格式")
        if not audio:
            raise VoiceAudioInvalid("录音为空，请重新录音")
        if len(audio) > self.max_audio_bytes:
            raise VoiceAudioTooLarge(
                f"录音超过 {self.max_audio_bytes // (1024 * 1024)} MB，请缩短后重试"
            )
        pcm = await asyncio.to_thread(self.converter.convert, audio)
        return await self.provider.transcribe(pcm)

    async def synthesize(self, text: str) -> tuple[bytes, str]:
        stripped = text.strip()
        if not stripped:
            raise VoiceTextInvalid("合成文本不能为空")
        if len(stripped) > self.max_tts_chars:
            raise VoiceTextTooLong(
                f"合成文本超过 {self.max_tts_chars} 个字符，请缩短后重试"
            )
        spoken = normalize_speech_text(stripped)
        if not spoken:
            raise VoiceTextInvalid("合成文本不包含可朗读内容")
        audio = await self.provider.synthesize(spoken)
        return audio, "audio/mpeg"


def create_voice_service(settings) -> VoiceService:
    if settings.VOICE_PROVIDER != "xfyun":
        raise VoiceConfigurationError(["VOICE_PROVIDER=xfyun"])
    required = {
        "XFYUN_VOICE_APP_ID": settings.XFYUN_VOICE_APP_ID,
        "XFYUN_VOICE_API_KEY": settings.XFYUN_VOICE_API_KEY,
        "XFYUN_VOICE_API_SECRET": settings.XFYUN_VOICE_API_SECRET,
        "XFYUN_ASR_ENDPOINT": settings.XFYUN_ASR_ENDPOINT,
        "XFYUN_TTS_ENDPOINT": settings.XFYUN_TTS_ENDPOINT,
        "XFYUN_TTS_VOICE": settings.XFYUN_TTS_VOICE,
    }
    missing = [name for name, value in required.items() if not str(value).strip()]
    if missing:
        raise VoiceConfigurationError(missing)
    credentials = VoiceCredentials(
        settings.XFYUN_VOICE_APP_ID,
        settings.XFYUN_VOICE_API_KEY,
        settings.XFYUN_VOICE_API_SECRET,
    )
    provider = XfyunVoiceProvider(
        credentials,
        asr_endpoint=settings.XFYUN_ASR_ENDPOINT,
        tts_endpoint=settings.XFYUN_TTS_ENDPOINT,
        voice=settings.XFYUN_TTS_VOICE,
        connect_timeout_seconds=settings.VOICE_CONNECT_TIMEOUT_SECONDS,
        request_timeout_seconds=settings.VOICE_REQUEST_TIMEOUT_SECONDS,
    )
    converter = FfmpegAudioConverter.discover(
        settings.VOICE_FFMPEG_PATH,
        max_audio_seconds=settings.VOICE_MAX_AUDIO_SECONDS,
        timeout_seconds=settings.VOICE_AUDIO_DECODE_TIMEOUT_SECONDS,
    )
    return VoiceService(
        provider,
        converter,
        max_audio_bytes=settings.VOICE_MAX_AUDIO_BYTES,
        max_tts_chars=settings.VOICE_TTS_MAX_CHARS,
    )
