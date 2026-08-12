"""Offline tests for voice conversion, service rules, and FastAPI contracts."""

import io
import subprocess
import unittest
import wave

from fastapi.testclient import TestClient

import web_server
from voice_service import (
    FfmpegAudioConverter,
    PcmAudio,
    VoiceAudioInvalid,
    VoiceAudioTooLarge,
    VoiceAudioTooLong,
    VoiceProviderTimeout,
    VoiceService,
    VoiceTextTooLong,
    VoiceUnsupportedMediaType,
)


def pcm_wav_bytes(
    *,
    duration_seconds: float = 0.1,
    sample_rate: int = 48000,
    channels: int = 2,
) -> bytes:
    frame_count = int(duration_seconds * sample_rate)
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * channels * frame_count)
    return output.getvalue()


class FakeProvider:
    def __init__(self):
        self.last_audio = None
        self.last_text = None

    async def transcribe(self, audio):
        self.last_audio = audio
        return "转写成功"

    async def synthesize(self, text):
        self.last_text = text
        return b"fake-mp3"


class StubConverter:
    max_audio_seconds = 60

    def __init__(self):
        self.last_audio = None

    def convert(self, audio):
        self.last_audio = audio
        return PcmAudio(b"\x00\x00" * 1600, 16000, 0.1)


class AudioConverterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.converter = FfmpegAudioConverter.discover(
            "",
            max_audio_seconds=1,
            timeout_seconds=10,
        )

    def test_ffmpeg_converts_stereo_48k_wav_to_mono_16k_pcm(self):
        converted = self.converter.convert(pcm_wav_bytes())

        self.assertEqual(converted.sample_rate, 16000)
        self.assertAlmostEqual(converted.duration_seconds, 0.1, places=2)
        self.assertEqual(len(converted.data), 3200)

    def test_ffmpeg_converts_mp4_aac_audio_to_mono_16k_pcm(self):
        encoded = subprocess.run(
            [
                self.converter.executable,
                "-v",
                "error",
                "-f",
                "wav",
                "-i",
                "pipe:0",
                "-c:a",
                "aac",
                "-b:a",
                "64k",
                "-f",
                "mp4",
                "-movflags",
                "frag_keyframe+empty_moov",
                "pipe:1",
            ],
            input=pcm_wav_bytes(sample_rate=16000, channels=1),
            capture_output=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(encoded.returncode, 0, encoded.stderr.decode(errors="replace"))

        converted = self.converter.convert(encoded.stdout)

        self.assertEqual(converted.sample_rate, 16000)
        self.assertGreater(converted.duration_seconds, 0)
        self.assertLess(converted.duration_seconds, 0.25)
        self.assertGreater(len(converted.data), 0)

    def test_ffmpeg_rejects_invalid_audio(self):
        with self.assertRaises(VoiceAudioInvalid):
            self.converter.convert(b"not an audio file")

    def test_ffmpeg_rejects_audio_over_duration_limit(self):
        with self.assertRaises(VoiceAudioTooLong):
            self.converter.convert(pcm_wav_bytes(duration_seconds=1.1, channels=1))


class VoiceServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.provider = FakeProvider()
        self.converter = StubConverter()
        self.service = VoiceService(
            self.provider,
            self.converter,
            max_audio_bytes=8,
            max_tts_chars=100,
        )

    async def test_transcribe_accepts_codec_parameter_and_passes_pcm(self):
        text = await self.service.transcribe(b"audio", "audio/webm;codecs=opus")

        self.assertEqual(text, "转写成功")
        self.assertEqual(self.converter.last_audio, b"audio")
        self.assertEqual(self.provider.last_audio.sample_rate, 16000)

    async def test_transcribe_accepts_ios_mp4_and_m4a_media_types(self):
        for content_type in (
            "audio/mp4;codecs=mp4a.40.2",
            "audio/m4a",
            "audio/x-m4a",
        ):
            with self.subTest(content_type=content_type):
                text = await self.service.transcribe(b"audio", content_type)
                self.assertEqual(text, "转写成功")

        self.assertEqual(self.converter.last_audio, b"audio")

    async def test_transcribe_rejects_unknown_type_empty_and_size_before_conversion(self):
        with self.assertRaises(VoiceUnsupportedMediaType):
            await self.service.transcribe(b"audio", "application/octet-stream")
        self.converter.last_audio = None
        with self.assertRaises(VoiceAudioInvalid):
            await self.service.transcribe(b"", "audio/webm")
        with self.assertRaises(VoiceAudioTooLarge):
            await self.service.transcribe(b"123456789", "audio/webm")
        self.assertIsNone(self.converter.last_audio)

    async def test_synthesize_cleans_markdown_urls_and_code(self):
        audio, content_type = await self.service.synthesize(
            "**说明** [题目](https://example.test/q/1) `dp[i]`\n```python\nprint(1)\n```"
        )

        self.assertEqual(audio, b"fake-mp3")
        self.assertEqual(content_type, "audio/mpeg")
        self.assertNotIn("https://", self.provider.last_text)
        self.assertNotIn("```", self.provider.last_text)
        self.assertIn("相关题目链接已显示在页面", self.provider.last_text)
        self.assertIn("代码段已显示在页面", self.provider.last_text)

    async def test_synthesize_rejects_text_over_configured_limit(self):
        with self.assertRaises(VoiceTextTooLong):
            await self.service.synthesize("文" * 101)


class FakeApiVoiceService:
    async def transcribe(self, audio, content_type):
        self.audio = audio
        self.content_type = content_type
        return "请讲讲动态规划"

    async def synthesize(self, text):
        self.text = text
        return b"ID3fake-mp3", "audio/mpeg"


class VoiceApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(web_server.app)
        self.original_service = web_server._voice_service
        self.original_error = web_server._voice_configuration_error
        self.service = FakeApiVoiceService()
        web_server._voice_service = self.service
        web_server._voice_configuration_error = None

    def tearDown(self):
        web_server._voice_service = self.original_service
        web_server._voice_configuration_error = self.original_error

    def test_capabilities_report_enabled_service_and_limits(self):
        response = self.client.get("/api/voice/capabilities")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["enabled"])
        self.assertTrue(response.json()["transcription"])
        self.assertGreater(response.json()["max_audio_bytes"], 0)

    def test_chat_waiting_video_returns_cached_mp4(self):
        response = self.client.get("/chat-waiting.mp4")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("video/mp4"))
        self.assertEqual(response.headers["cache-control"], "public, max-age=86400")
        self.assertGreater(len(response.content), 0)

    def test_transcription_contract_returns_confirmable_text(self):
        response = self.client.post(
            "/api/voice/transcriptions",
            files={"audio": ("sample.webm", b"webm-audio", "audio/webm")},
            data={"request_id": "voice-test-1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"text": "请讲讲动态规划", "request_id": "voice-test-1"},
        )
        self.assertEqual(response.headers["x-request-id"], "voice-test-1")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(self.service.audio, b"webm-audio")
        self.assertEqual(self.service.content_type, "audio/webm")

    def test_speech_contract_returns_uncached_audio(self):
        response = self.client.post(
            "/api/voice/speech",
            json={"text": "动态规划", "request_id": "voice-test-2"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ID3fake-mp3")
        self.assertTrue(response.headers["content-type"].startswith("audio/mpeg"))
        self.assertEqual(response.headers["x-request-id"], "voice-test-2")
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_disabled_service_preserves_capabilities_and_returns_503(self):
        web_server._voice_service = None
        capabilities = self.client.get("/api/voice/capabilities")
        transcription = self.client.post(
            "/api/voice/transcriptions",
            files={"audio": ("sample.webm", b"audio", "audio/webm")},
        )

        self.assertFalse(capabilities.json()["enabled"])
        self.assertEqual(transcription.status_code, 503)
        self.assertEqual(transcription.json()["error"]["code"], "voice_disabled")

    def test_provider_error_maps_to_stable_error_contract(self):
        class TimeoutService(FakeApiVoiceService):
            async def synthesize(self, text):
                del text
                raise VoiceProviderTimeout("讯飞语音合成响应超时")

        web_server._voice_service = TimeoutService()
        response = self.client.post(
            "/api/voice/speech",
            json={"text": "动态规划", "request_id": "voice-timeout"},
        )

        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json()["error"]["code"], "voice_provider_timeout")
        self.assertEqual(response.headers["x-request-id"], "voice-timeout")
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_request_id_rejects_header_unsafe_characters(self):
        response = self.client.post(
            "/api/voice/speech",
            json={"text": "动态规划", "request_id": "bad request id"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "validation_error")


if __name__ == "__main__":
    unittest.main()
