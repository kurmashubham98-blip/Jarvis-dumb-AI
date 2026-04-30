"""
Jarvis v2.0 — Speech-to-Text Engine (Cloud-Based)
====================================================
Uses Groq's Whisper API for high-accuracy cloud STT.
No local GPU needed — audio is sent to Groq and transcribed
via whisper-large-v3 for free.

Flow:
  Mic → Audio Chunk → Groq Whisper API → Text
"""

import asyncio
import io
import logging
import tempfile
import wave
import time
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("jarvis.voice.stt")


class STTEngine:
    """
    Cloud-based speech-to-text using Groq's Whisper API.
    Completely free, no local GPU required.
    """

    def __init__(self, groq_api_key: str, model: str = "whisper-large-v3", language: str = "en"):
        self._api_key = groq_api_key
        self._model = model
        self._language = language
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            try:
                from groq import Groq
                self._client = Groq(api_key=self._api_key)
                logger.info(f"Groq Whisper STT initialized: {self._model}")
            except Exception as e:
                logger.error(f"Groq STT init failed: {e}")
                raise

    async def transcribe(self, audio_data: np.ndarray, sample_rate: int = 16000) -> Optional[str]:
        """
        Transcribe audio data to text using Groq Whisper API.

        Args:
            audio_data: numpy array of audio samples (int16 or float32)
            sample_rate: Audio sample rate (default 16kHz)

        Returns:
            Transcribed text or None if failed
        """
        self._ensure_client()

        try:
            # Convert to WAV bytes in memory
            wav_bytes = self._to_wav_bytes(audio_data, sample_rate)

            # Send to Groq Whisper API
            start_time = time.time()

            transcription = await asyncio.to_thread(
                self._client.audio.transcriptions.create,
                file=("audio.wav", wav_bytes),
                model=self._model,
                language=self._language,
                response_format="text",
            )

            elapsed = time.time() - start_time
            text = transcription.strip() if isinstance(transcription, str) else transcription.text.strip()

            if text:
                logger.info(f"STT ({elapsed:.2f}s): \"{text[:80]}...\"")
            return text if text else None

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return None

    async def transcribe_file(self, file_path: str) -> Optional[str]:
        """Transcribe an audio file."""
        self._ensure_client()

        try:
            with open(file_path, "rb") as f:
                transcription = await asyncio.to_thread(
                    self._client.audio.transcriptions.create,
                    file=(Path(file_path).name, f.read()),
                    model=self._model,
                    language=self._language,
                    response_format="text",
                )

            text = transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
            return text if text else None

        except Exception as e:
            logger.error(f"File transcription failed: {e}")
            return None

    @staticmethod
    def _to_wav_bytes(audio_data: np.ndarray, sample_rate: int) -> bytes:
        """Convert numpy audio array to WAV bytes."""
        # Ensure int16 format
        if audio_data.dtype == np.float32 or audio_data.dtype == np.float64:
            audio_data = (audio_data * 32767).astype(np.int16)
        elif audio_data.dtype != np.int16:
            audio_data = audio_data.astype(np.int16)

        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data.tobytes())
        buf.seek(0)
        return buf.read()
