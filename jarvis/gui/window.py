"""
Jarvis v2.0 — HUD Window Manager (pywebview)
==============================================
Manages the transparent, frameless GUI overlay.
Provides a Python <-> JavaScript bridge to update the UI
in real-time from background threads.
"""

import logging
import threading
import time
from pathlib import Path

try:
    import webview
except ImportError:
    webview = None

from jarvis.config import PROJECT_ROOT

logger = logging.getLogger("jarvis.gui.window")


class APIBridge:
    """Methods exposed to JavaScript."""
    
    def __init__(self, brain, audio_manager):
        self.brain = brain
        self.audio = audio_manager
        self._window: webview.Window = None
        
    def set_window(self, window):
        self._window = window

    # Called from JS
    def js_submit_input(self, text: str):
        """User typed something in the HUD."""
        logger.info(f"HUD Input: {text}")
        if self.audio:
            # We use process_and_speak to send it through the standard pipeline
            import asyncio
            def _run():
                asyncio.run(self.audio.process_and_speak(text))
            threading.Thread(target=_run, daemon=True).start()
            
    def js_close_window(self):
        """User clicked close on HUD."""
        if self._window:
            self._window.hide()

    # Called from Python to update JS
    def py_update_status(self, text: str):
        if self._window:
            try:
                # Need to escape quotes properly for JS eval
                safe_text = text.replace("'", "\\'").replace("\n", " ")
                self._window.evaluate_js(f"updateStatus('{safe_text}');")
            except:
                pass
                
    def py_add_message(self, text: str, role: str):
        if self._window:
            try:
                # safe parsing for JS
                import json
                safe_text = json.dumps(text)
                self._window.evaluate_js(f"addMessage({safe_text}, '{role}');")
            except:
                pass


class HUDManager:
    """Manages the pywebview desktop overlay."""
    
    def __init__(self, config, brain, audio_manager=None):
        self.config = config
        self.brain = brain
        self.api = APIBridge(brain, audio_manager)
        self.window = None
        self._running = False
        
        # UI path
        self.ui_path = PROJECT_ROOT / "data" / "ui" / "index.html"
        
    def start(self):
        """Launch the HUD (Must be run in main thread)."""
        if not webview:
            logger.error("pywebview not installed! Cannot launch HUD.")
            return
            
        if not self.ui_path.exists():
            logger.error(f"UI file not found: {self.ui_path}")
            return

        logger.info("Starting holographic HUD...")
        self._running = True
        
        self.window = webview.create_window(
            title="Jarvis HUD",
            url=str(self.ui_path.absolute()),
            js_api=self.api,
            width=self.config.ui.width,
            height=self.config.ui.height,
            transparent=self.config.ui.transparent,
            frameless=self.config.ui.frameless,
            on_top=self.config.ui.on_top,
            easy_drag=True
        )
        
        self.api.set_window(self.window)
        
        # Hook into audio callbacks if available to update UI automatically
        if self.api.audio:
            self.api.audio.on_transcription(lambda t: self.api.py_add_message(t, "user"))
            self.api.audio.on_response(lambda r: self.api.py_add_message(r, "jarvis"))
            
        # Blocking call holding the main thread for the UI loop
        webview.start(debug=False)
        self._running = False

    def is_running(self):
        return self._running
