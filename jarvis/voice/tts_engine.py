"""
Jarvis v2.0 — Text-to-Speech Engine (edge-tts)
================================================
Uses Microsoft Edge's neural TTS service — the voices you liked.
High-quality, natural-sounding, FREE, and online.

Features:
  - Multiple voices (Guy, Aria, Jenny, etc.)
  - Adjustable rate, pitch, and volume
  - Streaming audio output (low latency)
  - Emotion-aware tone adaptation
  - Interrupt support (stop mid-sentence)
"""

import asyncio
import io
import logging
import tempfile
from pathlib import Path
from typing import Optional
import numpy as np

logger = logging.getLogger("jarvis.voice.tts")


class TTSEngine:
    """
    Text-to-Speech using edge-tts (Microsoft Edge neural voices).
    Produces natural, expressive speech for free.
    """

    # Available voice profiles for different moods
    VOICES = {
        "default": "en-GB-RyanNeural",       # Jarvis default — British, composed
        "serious": "en-GB-RyanNeural",        # Same voice, slower rate
        "casual": "en-US-ChristopherNeural", # More relaxed male voice
        "alert": "en-GB-RyanNeural",          # Same voice, urgent tone
        "female": "en-US-AriaNeural",        # Female alternative
        "american": "en-US-GuyNeural",       # American alternative
    }

    def __init__(
        self,
        voice: str = "en-GB-RyanNeural",
        rate: str = "+10%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
    ):
        self._voice = voice
        self._rate = rate
        self._volume = volume
        self._pitch = pitch

        self._is_speaking = False
        self._cancel_flag = False
        self._current_process = None

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    async def speak(self, text: str, voice_override: str = None, blocking: bool = True) -> bool:
        """
        Speak text aloud using edge-tts.

        Args:
            text: Text to speak
            voice_override: Temporary voice change (e.g., for different moods)
            blocking: If True, wait until speech finishes

        Returns:
            True if speech completed, False if interrupted or failed
        """
        if not text or not text.strip():
            return False

        self._is_speaking = True
        self._cancel_flag = False

        try:
            import edge_tts
            import re

            voice = voice_override or self._voice
            
            # --- Markdown Sanitization for TTS ---
            # Remove giant code blocks, replace with a spoken summary
            clean_text = re.sub(r'```.*?```', ' I have provided the code block for you. ', text, flags=re.DOTALL)
            # Remove inline code ticks
            clean_text = clean_text.replace('`', '')
            # Remove heading hashes
            clean_text = re.sub(r'#+\s+', '', clean_text)
            # Remove bold/italic stars
            clean_text = clean_text.replace('*', '')
            # Remove URLs to avoid spelling them out letter by letter
            clean_text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', 'that link', clean_text)
            
            # If nothing is left after sanitization, or it's too short, speak the original (with basic replacement)
            if not clean_text.strip():
                clean_text = "I have your response ready."

            communicate = edge_tts.Communicate(
                text=clean_text.strip(),
                voice=voice,
                rate=self._rate,
                volume=self._volume,
                pitch=self._pitch,
            )

            # Generate audio to temp file
            temp_path = Path(tempfile.gettempdir()) / "jarvis_speech.mp3"

            await communicate.save(str(temp_path))

            if self._cancel_flag:
                return False

            # Play audio
            if blocking:
                await self._play_audio(str(temp_path))
            else:
                asyncio.create_task(self._play_audio(str(temp_path)))

            return not self._cancel_flag

        except Exception as e:
            logger.error(f"TTS failed: {e}")
            return False
        finally:
            self._is_speaking = False

    async def speak_with_mood(self, text: str, mood: str = "default") -> bool:
        """
        Speak with an emotion-adapted voice.

        Moods: default, serious, casual, alert, british
        """
        voice = self.VOICES.get(mood, self.VOICES["default"])

        # Adjust rate based on mood
        rate_map = {
            "default": "+10%",
            "serious": "+0%",      # Slower, measured
            "casual": "+15%",      # Slightly faster, relaxed
            "alert": "+20%",       # Urgent, quick
            "british": "+5%",      # Slightly formal pace
        }
        original_rate = self._rate
        self._rate = rate_map.get(mood, "+10%")

        result = await self.speak(text, voice_override=voice)

        # Restore original rate
        self._rate = original_rate
        return result

    async def stop(self):
        """Interrupt current speech immediately."""
        self._cancel_flag = True
        if self._current_process:
            try:
                self._current_process.terminate()
            except Exception:
                pass
        self._is_speaking = False
        logger.info("Speech interrupted")

    async def _play_audio(self, file_path: str):
        """Play an audio file using Pygame (native MP3 support)."""
        try:
            import pygame
            
            # Initialize mixer if not already initialized
            if not pygame.mixer.get_init():
                pygame.mixer.init()
                
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()
            
            # Wait for playback to finish
            while pygame.mixer.music.get_busy():
                if self._cancel_flag:
                    pygame.mixer.music.stop()
                    break
                await asyncio.sleep(0.1)
                
            pygame.mixer.music.unload()

        except ImportError:
            logger.error("Pygame is not installed. Run: pip install pygame")
        except Exception as e:
            logger.error(f"Audio playback failed: {e}")
        finally:
            # Clean up temp file
            try:
                Path(file_path).unlink(missing_ok=True)
            except Exception:
                pass

    def set_voice(self, voice: str):
        """Change the TTS voice."""
        self._voice = voice
        logger.info(f"TTS voice changed to: {voice}")

    def set_rate(self, rate: str):
        """Change the speech rate (e.g., '+10%', '-5%')."""
        self._rate = rate

    @staticmethod
    async def list_voices() -> list[dict]:
        """List all available edge-tts voices."""
        try:
            import edge_tts
            voices = await edge_tts.list_voices()
            return [
                {
                    "name": v["ShortName"],
                    "language": v["Locale"],
                    "gender": v["Gender"],
                }
                for v in voices
                if v["Locale"].startswith("en-")  # English voices only
            ]
        except Exception as e:
            logger.error(f"Failed to list voices: {e}")
            return []
