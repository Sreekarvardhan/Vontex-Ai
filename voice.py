"""
voice.py — Speech-to-text (Whisper) and text-to-speech (ElevenLabs).

STT:  Audio bytes -> transcript string
TTS:  Text string -> audio bytes (ulaw 8kHz for Twilio compatibility)
"""

import base64
from io import BytesIO

import httpx
from openai import AsyncOpenAI

from config import settings

_openai = AsyncOpenAI(api_key=settings.openai_api_key)


# ═══════════════════════════════════════════════════════════════════════════
# SPEECH -> TEXT  (OpenAI Whisper)
# ═══════════════════════════════════════════════════════════════════════════

async def transcribe_audio(audio_bytes: bytes) -> str:
    """
    Transcribe raw audio bytes to text using OpenAI Whisper.
    Twilio sends ulaw 8kHz PCM; we wrap it in a WAV container before sending.
    Returns empty string on failure (caller silence or noise).
    """
    if len(audio_bytes) < 1600:
        return ""

    try:
        wav_bytes = _mulaw_to_wav(audio_bytes)
        buf = BytesIO(wav_bytes)
        buf.name = "audio.wav"

        transcript = await _openai.audio.transcriptions.create(
            model="whisper-1",
            file=buf,
            language="en"
        )
        text = transcript.text.strip()
        return text if len(text) > 1 else ""

    except Exception as e:
        print(f"[transcribe_audio] error: {e}")
        return ""


# ═══════════════════════════════════════════════════════════════════════════
# TEXT -> SPEECH  (ElevenLabs)
# ═══════════════════════════════════════════════════════════════════════════

async def synthesize_speech(text: str) -> bytes:
    """
    Convert text to speech using ElevenLabs Turbo v2 (lowest latency).
    Returns raw audio bytes in ulaw 8kHz format (Twilio-native).
    Returns empty bytes on failure.
    """
    if not text or not text.strip():
        return b""

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{settings.elevenlabs_voice_id}/stream",
                headers={
                    "xi-api-key":   settings.elevenlabs_api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "text":     text,
                    "model_id": "eleven_turbo_v2",
                    "voice_settings": {
                        "stability":        0.5,
                        "similarity_boost": 0.8,
                        "style":            0.0,
                        "use_speaker_boost": True
                    },
                    "output_format": "ulaw_8000"
                }
            )
            r.raise_for_status()
            return r.content

    except Exception as e:
        print(f"[synthesize_speech] error: {e}")
        return b""


# ═══════════════════════════════════════════════════════════════════════════
# TWILIO AUDIO HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def encode_for_twilio(audio_bytes: bytes) -> str:
    """Base64-encode audio bytes for the Twilio Media Stream payload."""
    return base64.b64encode(audio_bytes).decode("utf-8")


def decode_from_twilio(payload: str) -> bytes:
    """Decode a base64 Twilio Media Stream payload to raw audio bytes."""
    return base64.b64decode(payload)


# ═══════════════════════════════════════════════════════════════════════════
# INTERNAL: ulaw -> WAV wrapper
# ═══════════════════════════════════════════════════════════════════════════

def _mulaw_to_wav(mulaw_bytes: bytes) -> bytes:
    """
    Wrap raw ulaw 8000 Hz mono PCM bytes in a minimal WAV header.
    Whisper accepts WAV files, but Twilio sends raw PCM.
    """
    import struct

    num_channels   = 1
    sample_rate    = 8000
    bits_per_samp  = 8
    audio_format   = 7

    byte_rate   = sample_rate * num_channels * bits_per_samp // 8
    block_align = num_channels * bits_per_samp // 8
    data_size   = len(mulaw_bytes)
    chunk_size  = 36 + data_size

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", chunk_size, b"WAVE",
        b"fmt ", 16,
        audio_format, num_channels, sample_rate,
        byte_rate, block_align, bits_per_samp,
        b"data", data_size
    )
    return header + mulaw_bytes