"""
Jarvis v2.0 — Audio Manager
==============================
Handles microphone input, speaker output, and the real-time voice pipeline.

Pipeline:
  1. Wake word detection (always listening, low CPU)
  2. On activation → record audio chunk
  3. Send to Groq Whisper (cloud STT)
  4. Feed text to Brain
  5. Brain response → edge-tts → speaker
  6. Listen for interrupt or next command

Features:
  - Continuous background listening
  - Voice Activity Detection (VAD) — know when user stops talking
  - Interrupt handling — user can cut off Jarvis mid-sentence
  - Audio energy detection — ignore silence
"""

import asyncio
import logging
import time
import threading
import queue
from typing import Optional, Callable

import numpy as np

logger = logging.getLogger("jarvis.voice.audio")


class AudioManager:
    """
    Manages the full audio pipeline:
    Microphone → Wake Word → STT → Brain → TTS → Speaker
    """

    def __init__(
        self,
        stt_engine,
        tts_engine,
        brain,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_duration_ms: int = 80,
        silence_threshold: float = 0.01,
        silence_duration: float = 1.5,  # Seconds of silence to end recording
        max_recording_seconds: float = 30.0,
    ):
        self.stt = stt_engine
        self.tts = tts_engine
        self.brain = brain
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = int(sample_rate * chunk_duration_ms / 1000)
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self.max_recording_seconds = max_recording_seconds

        # State
        self._listening = False
        self._recording = False
        self._wake_word_active = True
        self._stream = None
        self._audio_queue = queue.Queue()
        self._on_wake_callback: Optional[Callable] = None
        self._on_transcription_callback: Optional[Callable] = None
        self._on_response_callback: Optional[Callable] = None

    # ── Event Callbacks ─────────────────────────────────────────

    def on_wake(self, callback: Callable):
        """Register callback for wake word detection."""
        self._on_wake_callback = callback

    def on_transcription(self, callback: Callable):
        """Register callback when user speech is transcribed."""
        self._on_transcription_callback = callback

    def on_response(self, callback: Callable):
        """Register callback when Jarvis responds."""
        self._on_response_callback = callback

    # ── Microphone Control ──────────────────────────────────────

    async def start_listening(self):
        """Start the microphone and begin the listen → process loop."""
        if self._listening:
            return

        self._listening = True
        logger.info("Audio manager: listening started")

        try:
            import sounddevice as sd

            def audio_callback(indata, frames, time_info, status):
                if status:
                    logger.debug(f"Audio status: {status}")
                self._audio_queue.put(indata.copy())

            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=np.float32,
                blocksize=self.chunk_size,
                callback=audio_callback,
            )
            self._stream.start()

            # Main loop
            while self._listening:
                await self._process_audio_loop()

        except ImportError:
            logger.error("sounddevice not installed! Voice input disabled.")
        except Exception as e:
            logger.error(f"Audio manager error: {e}")
        finally:
            self._stop_stream()

    def stop_listening(self):
        """Stop listening."""
        self._listening = False
        self._stop_stream()
        logger.info("Audio manager: listening stopped")

    def _stop_stream(self):
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    # ── Audio Processing Loop ───────────────────────────────────

    async def _process_audio_loop(self):
        """Main processing loop — runs continuously while listening."""
        # Check for audio in queue
        try:
            chunk = self._audio_queue.get(timeout=0.1)
        except queue.Empty:
            await asyncio.sleep(0.05)
            return

        energy = np.abs(chunk).mean()

        # If wake word mode, check for wake word
        if self._wake_word_active:
            # For now, use energy-based activation
            # openWakeWord integration will replace this
            if energy > self.silence_threshold * 3:
                self._wake_word_active = False
                if self._on_wake_callback:
                    self._on_wake_callback()
                logger.info("Voice activated — recording...")
                await self._record_and_process()
                self._wake_word_active = True
        else:
            await self._record_and_process()

    async def _record_and_process(self):
        """Record audio until silence, transcribe, and process."""
        self._recording = True
        audio_chunks = []
        silence_start = None
        recording_start = time.time()

        try:
            while self._recording:
                try:
                    chunk = self._audio_queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                audio_chunks.append(chunk)
                energy = np.abs(chunk).mean()

                # Check for silence (end of speech)
                if energy < self.silence_threshold:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start > self.silence_duration:
                        logger.info("Silence detected — processing speech")
                        break
                else:
                    silence_start = None

                # Max recording limit
                if time.time() - recording_start > self.max_recording_seconds:
                    logger.info("Max recording time reached")
                    break

        finally:
            self._recording = False

        if not audio_chunks:
            return

        # Combine audio chunks
        audio_data = np.concatenate(audio_chunks, axis=0).flatten()

        # Check if there's actually speech (not just noise)
        if np.abs(audio_data).mean() < self.silence_threshold * 0.5:
            logger.debug("Audio too quiet — ignoring")
            return

        # Transcribe via cloud STT
        text = await self.stt.transcribe(audio_data, self.sample_rate)

        if not text:
            logger.debug("Empty transcription — ignoring")
            return

        logger.info(f"User said: \"{text}\"")

        if self._on_transcription_callback:
            self._on_transcription_callback(text)

        # Check for interrupt/stop commands
        if self._is_stop_command(text):
            if self.tts.is_speaking:
                await self.tts.stop()
            return

        # Process through Brain
        response = await self.brain.think(text)
        logger.info(f"Jarvis: \"{response[:100]}...\"")

        if self._on_response_callback:
            self._on_response_callback(response)

        # Speak the response
        await self.tts.speak(response)

    @staticmethod
    def _is_stop_command(text: str) -> bool:
        """Check if the user wants to interrupt Jarvis."""
        stop_phrases = [
            "stop", "shut up", "be quiet", "enough", "cancel",
            "never mind", "nevermind", "okay stop", "jarvis stop",
            "that's enough", "quiet",
        ]
        return text.lower().strip().rstrip('.!') in stop_phrases

    # ── Manual Input Mode ───────────────────────────────────────

    async def process_text_input(self, text: str) -> str:
        """
        Process text input directly (from HUD or terminal).
        Bypass the mic/STT pipeline.
        """
        if self._on_transcription_callback:
            self._on_transcription_callback(text)

        response = await self.brain.think(text)

        if self._on_response_callback:
            self._on_response_callback(response)

        return response

    async def process_and_speak(self, text: str) -> str:
        """Process text input and speak the response."""
        response = await self.process_text_input(text)
        await self.tts.speak(response)
        return response

    # ── Status ──────────────────────────────────────────────────

    def get_status(self) -> dict:
        return {
            "listening": self._listening,
            "recording": self._recording,
            "wake_word_active": self._wake_word_active,
            "tts_speaking": self.tts.is_speaking,
        }
