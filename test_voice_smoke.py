"""Offline protocol tests for the standalone XFYUN voice smoke tool."""

import base64
import os
import tempfile
import unittest
import wave
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from voice_service import (
    VoiceCredentials,
    VoiceError,
    _asr_text,
    asr_frame,
    authorization_url,
    tts_request,
)
from voice_smoke import load_pcm_wav


class VoiceSmokeProtocolTests(unittest.TestCase):
    def setUp(self):
        self.credentials = VoiceCredentials("app-id", "api-key", "api-secret")

    def test_authorization_url_contains_signed_fields_without_secret(self):
        url = authorization_url(
            "wss://iat-api.xfyun.cn/v2/iat",
            self.credentials.api_key,
            self.credentials.api_secret,
            now=datetime(2026, 8, 5, 3, 0, tzinfo=timezone.utc),
        )
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        authorization = base64.b64decode(query["authorization"][0]).decode("utf-8")

        self.assertEqual(parsed.scheme, "wss")
        self.assertEqual(parsed.hostname, "iat-api.xfyun.cn")
        self.assertEqual(query["host"], ["iat-api.xfyun.cn"])
        self.assertIn('api_key="api-key"', authorization)
        self.assertIn('headers="host date request-line"', authorization)
        self.assertNotIn("api-secret", url)
        self.assertNotIn("api-secret", authorization)

    def test_authorization_rejects_non_websocket_endpoint(self):
        with self.assertRaisesRegex(VoiceError, "wss"):
            authorization_url("https://example.test/asr", "key", "secret")

    def test_asr_first_frame_contains_protocol_context(self):
        payload = asr_frame(self.credentials, b"\x01\x02", 16000, 0)
        self.assertEqual(payload["common"], {"app_id": "app-id"})
        self.assertEqual(payload["business"]["language"], "zh_cn")
        self.assertEqual(payload["data"]["format"], "audio/L16;rate=16000")
        self.assertEqual(payload["data"]["encoding"], "raw")
        self.assertEqual(base64.b64decode(payload["data"]["audio"]), b"\x01\x02")

    def test_asr_followup_frame_does_not_repeat_context(self):
        payload = asr_frame(self.credentials, b"audio", 8000, 1)
        self.assertNotIn("common", payload)
        self.assertNotIn("business", payload)

    def test_asr_text_selects_top_candidate(self):
        payload = {
            "data": {
                "result": {
                    "ws": [
                        {"cw": [{"w": "动态"}, {"w": "洞太"}]},
                        {"cw": [{"w": "规划"}]},
                    ]
                }
            }
        }
        self.assertEqual(_asr_text(payload), "动态规划")

    def test_tts_request_uses_streaming_mp3_and_utf8_text(self):
        payload = tts_request(self.credentials, "讲讲动态规划", "xiaoyan")
        self.assertEqual(payload["business"]["aue"], "lame")
        self.assertEqual(payload["business"]["sfl"], 1)
        self.assertEqual(payload["business"]["vcn"], "xiaoyan")
        self.assertEqual(
            base64.b64decode(payload["data"]["text"]).decode("utf-8"),
            "讲讲动态规划",
        )

    def test_tts_request_rejects_empty_and_oversize_text(self):
        with self.assertRaises(VoiceError):
            tts_request(self.credentials, "", "xiaoyan")
        with self.assertRaises(VoiceError):
            tts_request(self.credentials, "中" * 2667, "xiaoyan")

    def test_load_pcm_wav_accepts_provider_format(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.wav"
            with wave.open(str(path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(b"\x00\x00" * 1600)

            audio = load_pcm_wav(path)

        self.assertEqual(audio.sample_rate, 16000)
        self.assertAlmostEqual(audio.duration_seconds, 0.1)
        self.assertEqual(len(audio.data), 3200)

    def test_load_pcm_wav_rejects_stereo(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stereo.wav"
            with wave.open(str(path), "wb") as wav_file:
                wav_file.setnchannels(2)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(b"\x00\x00\x00\x00" * 100)

            with self.assertRaisesRegex(VoiceError, "mono"):
                load_pcm_wav(path)

    def test_missing_credential_error_names_keys_without_values(self):
        environment = {
            "XFYUN_VOICE_APP_ID": "secret-app",
            "XFYUN_VOICE_API_KEY": "",
            "XFYUN_VOICE_API_SECRET": "",
        }
        with (
            patch.dict(os.environ, environment, clear=True),
            self.assertRaises(VoiceError) as raised,
        ):
            VoiceCredentials.from_environment()

        message = str(raised.exception)
        self.assertIn("XFYUN_VOICE_API_KEY", message)
        self.assertIn("XFYUN_VOICE_API_SECRET", message)
        self.assertNotIn("secret-app", message)


if __name__ == "__main__":
    unittest.main()
