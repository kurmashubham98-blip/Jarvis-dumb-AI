"""
Jarvis v2.0 — Vision System (Screen Reader)
=============================================
Allows Jarvis to "see" the screen.
Fast capture via mss, advanced visual comprehension via Gemini Vision.
"""

import asyncio
import io
import logging
import platform
import base64
from typing import Optional, Dict, Any

from PIL import Image

logger = logging.getLogger("jarvis.vision.screen")


class VisionEngine:
    """Handles everything Jarvis can see."""

    def __init__(self, gemini_api_key: str):
        self._api_key = gemini_api_key
        self._client = None
        self._model = None
        
    def _ensure_client(self):
        if self._client is None and self._api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self._api_key)
                self._client = genai
                # Ensure we use an image-capable model
                self._model = genai.GenerativeModel('gemini-2.5-flash')
                logger.info("Vision Engine initialized")
            except Exception as e:
                logger.error(f"Vision Engine init failed: {e}")
                
    async def capture_screen(self) -> Optional[Image.Image]:
        """Capture the primary display rapidly using mss."""
        try:
            import mss
            with mss.mss() as sct:
                # Monitor 1 is usually the primary display
                monitor = sct.monitors[1]
                sct_img = sct.grab(monitor)
                # Convert to PIL Image
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                return img
        except ImportError:
            logger.error("mss not installed. Cannot capture screen.")
            return None
        except Exception as e:
            logger.error(f"Screen capture failed: {e}")
            return None

    async def analyze_image(self, img: Image.Image, prompt: str) -> str:
        """Send PIL Image + Prompt to Gemini Vision API."""
        self._ensure_client()
        if not self._model:
            return "Vision systems are offline due to API configuration issues."
            
        try:
            logger.info("Sending image to Gemini Vision API")
            
            # Compress image to save bandwidth and API limits while retaining context
            # Resize if too large
            max_size = 1920
            if img.width > max_size or img.height > max_size:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                
            response = await asyncio.to_thread(
                self._model.generate_content,
                [prompt, img]
            )
            
            return response.text
        except Exception as e:
            logger.error(f"Vision analysis failed: {e}")
            return f"I experienced an error analyzing the image: {e}"
            
    async def analyze_screen(self, prompt: str = "Describe what is on my screen right now in concise detail.") -> str:
        """Capture the screen and analyze it in one go."""
        img = await self.capture_screen()
        if not img:
            return "I am currently blind to the screen (capture failed)."
            
        return await self.analyze_image(img, prompt)
        
    async def read_screen_text(self) -> str:
        """OCR to extract raw text rapidly (without LLM if Tesseract is available)."""
        img = await self.capture_screen()
        if not img:
            return ""
            
        try:
            import pytesseract
            # Need to specify tesseract path on Windows usually
            if platform.system() == "Windows":
                pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
            text = pytesseract.image_to_string(img)
            return text.strip()
        except ImportError:
            return await self.analyze_image(img, "Extract all the text you can see in this image. Only output the text.")
        except Exception as e:
            # Fallback to Gemini if pure OCR fails
            return await self.analyze_image(img, "Extract all the text you can see in this image. Only output the text.")
