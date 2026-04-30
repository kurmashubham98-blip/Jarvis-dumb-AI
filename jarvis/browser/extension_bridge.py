"""
Jarvis v2.0 — Extension Bridge (WebSocket Server)
====================================================
LEVEL 3 browser control — real-time bidirectional communication
between Jarvis and a custom browser extension.

The Extension Bridge enables:
  - LIVE page context (Jarvis knows what you're reading RIGHT NOW)
  - Real-time DOM monitoring (detect page changes instantly)
  - Script injection into the active page
  - Tab event hooks (new tab, close tab, URL change)
  - Content extraction without needing Playwright

Architecture:
  Jarvis (Python) ←WebSocket→ Chrome Extension (JS)
       ↓                              ↓
  Process commands              Read DOM, inject scripts
  Generate responses            Monitor tab changes
  Route to agents               Send page data back

The extension connects to this server on ws://localhost:9741
"""

import asyncio
import json
import logging
import time
from typing import Optional, Callable
from dataclasses import dataclass, field

logger = logging.getLogger("jarvis.browser.bridge")

# WebSocket port for extension communication
BRIDGE_PORT = 9741


@dataclass
class LivePageState:
    """Real-time state of the user's active browser tab."""
    url: str = ""
    title: str = ""
    domain: str = ""
    text_content: str = ""
    selected_text: str = ""
    tab_count: int = 0
    is_playing_media: bool = False
    scroll_position: float = 0.0  # 0.0 to 1.0
    last_updated: float = 0.0

    @property
    def is_stale(self) -> bool:
        return time.time() - self.last_updated > 10


class ExtensionBridge:
    """
    WebSocket server that communicates with the Jarvis Chrome Extension.
    Provides real-time browser awareness and control.
    """

    def __init__(self, port: int = BRIDGE_PORT):
        self.port = port
        self._server = None
        self._client = None  # The connected extension
        self._running = False
        self._page_state = LivePageState()
        self._event_callbacks: dict[str, list[Callable]] = {}
        self._pending_responses: dict[str, asyncio.Future] = {}
        self._request_counter = 0

    @property
    def is_connected(self) -> bool:
        """Is a browser extension currently connected?"""
        return self._client is not None

    @property
    def page_state(self) -> LivePageState:
        """Get the current live page state."""
        return self._page_state

    async def start(self):
        """Start the WebSocket server."""
        try:
            import websockets
            self._server = await websockets.serve(
                self._handle_connection,
                "localhost",
                self.port,
                ping_interval=30,
                ping_timeout=10,
            )
            self._running = True
            logger.info(f"Extension bridge started on ws://localhost:{self.port}")
        except ImportError:
            logger.warning("websockets not installed — extension bridge disabled")
            logger.warning("Install with: pip install websockets")
        except Exception as e:
            logger.error(f"Extension bridge failed to start: {e}")

    async def stop(self):
        """Stop the WebSocket server."""
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        logger.info("Extension bridge stopped")

    async def _handle_connection(self, websocket, path=None):
        """Handle a new extension connection."""
        self._client = websocket
        logger.info("Browser extension connected")

        try:
            async for message in websocket:
                await self._handle_message(message)
        except Exception as e:
            logger.error(f"Extension connection error: {e}")
        finally:
            self._client = None
            logger.info("Browser extension disconnected")

    async def _handle_message(self, raw: str):
        """Process an incoming message from the extension."""
        try:
            data = json.loads(raw)
            msg_type = data.get("type", "")

            if msg_type == "page_update":
                # Extension is reporting the current page state
                self._page_state = LivePageState(
                    url=data.get("url", ""),
                    title=data.get("title", ""),
                    domain=data.get("domain", ""),
                    text_content=data.get("text", "")[:15000],
                    selected_text=data.get("selectedText", ""),
                    tab_count=data.get("tabCount", 0),
                    is_playing_media=data.get("isPlayingMedia", False),
                    scroll_position=data.get("scrollPosition", 0),
                    last_updated=time.time(),
                )
                logger.debug(f"Page update: {self._page_state.title}")

            elif msg_type == "tab_event":
                event = data.get("event", "")
                self._fire_event(f"tab_{event}", data)

            elif msg_type == "selection_change":
                self._page_state.selected_text = data.get("text", "")

            elif msg_type == "response":
                # Response to a command we sent
                req_id = data.get("requestId", "")
                if req_id in self._pending_responses:
                    self._pending_responses[req_id].set_result(data.get("result"))

            elif msg_type == "error":
                logger.error(f"Extension error: {data.get('message', 'unknown')}")

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from extension: {raw[:100]}")
        except Exception as e:
            logger.error(f"Message handling error: {e}")

    async def send_command(self, command: str, params: dict = None, timeout: float = 10.0) -> Optional[any]:
        """
        Send a command to the browser extension and wait for response.
        
        Commands:
          - get_page_content: Extract full page content
          - get_selected_text: Get currently selected text
          - execute_script: Run JavaScript on the page
          - inject_css: Add CSS to the page
          - get_tab_info: Get info about all tabs
          - focus_tab: Switch to a specific tab
          - close_tab: Close a tab
          - scroll_to: Scroll to a position
          - highlight_element: Highlight an element (visual feedback)
        """
        if not self.is_connected:
            logger.warning("Extension not connected — command dropped")
            return None

        self._request_counter += 1
        req_id = f"req_{self._request_counter}"

        message = json.dumps({
            "type": "command",
            "requestId": req_id,
            "command": command,
            "params": params or {},
        })

        # Create a future for the response
        future = asyncio.get_event_loop().create_future()
        self._pending_responses[req_id] = future

        try:
            await self._client.send(message)
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Command '{command}' timed out")
            return None
        except Exception as e:
            logger.error(f"Command '{command}' failed: {e}")
            return None
        finally:
            self._pending_responses.pop(req_id, None)

    # ── High-Level Commands ─────────────────────────────────────

    async def get_live_content(self) -> str:
        """Get the full text content of the current page via extension."""
        if self.is_connected:
            result = await self.send_command("get_page_content")
            if result:
                return result
        # Fallback to cached state
        return self._page_state.text_content

    async def get_selected_text(self) -> str:
        """Get whatever text the user has selected on the page."""
        if self.is_connected:
            result = await self.send_command("get_selected_text")
            if result:
                return result
        return self._page_state.selected_text

    async def inject_script(self, script: str) -> any:
        """Execute JavaScript on the active page via extension."""
        return await self.send_command("execute_script", {"script": script})

    async def inject_css(self, css: str) -> bool:
        """Inject CSS into the active page."""
        result = await self.send_command("inject_css", {"css": css})
        return result is not None

    async def highlight_element(self, selector: str) -> bool:
        """Highlight an element on the page (visual feedback for user)."""
        result = await self.send_command("highlight_element", {"selector": selector})
        return result is not None

    async def get_all_tabs(self) -> list:
        """Get info about all open tabs."""
        result = await self.send_command("get_tab_info")
        return result if result else []

    # ── Event System ────────────────────────────────────────────

    def on(self, event: str, callback: Callable):
        """Register a callback for browser events."""
        if event not in self._event_callbacks:
            self._event_callbacks[event] = []
        self._event_callbacks[event].append(callback)

    def _fire_event(self, event: str, data: dict):
        """Fire registered callbacks for an event."""
        for cb in self._event_callbacks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(cb):
                    asyncio.create_task(cb(data))
                else:
                    cb(data)
            except Exception as e:
                logger.error(f"Event callback error ({event}): {e}")

    def get_status(self) -> dict:
        """Get bridge status for diagnostics."""
        return {
            "running": self._running,
            "connected": self.is_connected,
            "page": {
                "url": self._page_state.url,
                "title": self._page_state.title,
                "domain": self._page_state.domain,
                "stale": self._page_state.is_stale,
            },
            "port": self.port,
        }
