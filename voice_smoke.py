"""Standalone CLI for validating the production XFYUN voice provider."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import wave
from pathlib import Path

from dotenv import load_dotenv

from voice_service import (
    DEFAULT_ASR_ENDPOINT,
    DEFAULT_TTS_ENDPOINT,
    PcmAudio,
    VoiceConfigurationError,
    VoiceCredentials,
    VoiceError,
    XfyunVoiceProvider,
)

BASE_DIR = Path(__file__).parent
MAX_AUDIO_SECONDS = 60
VoiceSmokeError = VoiceError


def load_pcm_wav(path: Path) -> PcmAudio:
    """Load provider-compatible mono, 16-bit, 8/16 kHz PCM from a WAV file."""
    try:
        with wave.open(str(path), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
            compression = wav_file.getcomptype()
            data = wav_file.readframes(frame_count)
    except (FileNotFoundError, wave.Error, OSError) as exc:
        raise VoiceError(f"cannot read WAV audio: {path}") from exc

    if compression != "NONE":
        raise VoiceError("ASR smoke audio must be uncompressed PCM WAV")
    if channels != 1 or sample_width != 2 or sample_rate not in {8000, 16000}:
        raise VoiceError(
            "ASR smoke audio must be mono, 16-bit PCM at 8000 or 16000 Hz"
        )
    if not data or frame_count <= 0:
        raise VoiceError("ASR smoke audio is empty")
    duration = frame_count / sample_rate
    if duration > MAX_AUDIO_SECONDS:
        raise VoiceError(f"ASR smoke audio exceeds {MAX_AUDIO_SECONDS} seconds")
    return PcmAudio(data=data, sample_rate=sample_rate, duration_seconds=duration)


def _settings() -> tuple[XfyunVoiceProvider, str]:
    load_dotenv(BASE_DIR / ".env", override=False)
    credentials = VoiceCredentials.from_environment()
    asr_endpoint = os.environ.get("XFYUN_ASR_ENDPOINT", DEFAULT_ASR_ENDPOINT).strip()
    tts_endpoint = os.environ.get("XFYUN_TTS_ENDPOINT", DEFAULT_TTS_ENDPOINT).strip()
    voice = os.environ.get("XFYUN_TTS_VOICE", "xiaoyan").strip()
    missing = []
    if not asr_endpoint:
        missing.append("XFYUN_ASR_ENDPOINT")
    if not tts_endpoint:
        missing.append("XFYUN_TTS_ENDPOINT")
    if not voice:
        missing.append("XFYUN_TTS_VOICE")
    if missing:
        raise VoiceConfigurationError(missing)
    return (
        XfyunVoiceProvider(
            credentials,
            asr_endpoint=asr_endpoint,
            tts_endpoint=tts_endpoint,
            voice=voice,
        ),
        voice,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate XFYUN ASR and TTS credentials")
    parser.add_argument("--timeout", type=float, default=45, help="request timeout in seconds")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="check configuration without contacting XFYUN")

    asr = subparsers.add_parser("asr", help="transcribe a PCM WAV sample")
    asr.add_argument("audio", type=Path)

    tts = subparsers.add_parser("tts", help="synthesize an MP3 sample")
    tts.add_argument("--text", required=True)
    tts.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser("verify", help="run ASR and TTS in one command")
    verify.add_argument("audio", type=Path)
    verify.add_argument("--text", required=True)
    verify.add_argument("--output", type=Path, required=True)
    return parser


async def _run(args: argparse.Namespace) -> None:
    provider, voice = _settings()
    provider.request_timeout_seconds = args.timeout
    if args.command == "check":
        print("XFYUN voice configuration is complete (values not displayed).")
        return
    if args.command in {"asr", "verify"}:
        audio = load_pcm_wav(args.audio)
        text = await provider.transcribe(audio)
        print(f"ASR ({audio.duration_seconds:.2f}s): {text}")
    if args.command in {"tts", "verify"}:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        speech = await provider.synthesize(args.text)
        output.write_bytes(speech)
        print(f"TTS ({voice}): wrote {len(speech)} bytes to {output}")


def main() -> int:
    args = _parser().parse_args()
    try:
        asyncio.run(_run(args))
    except VoiceError as exc:
        print(f"voice smoke failed: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
