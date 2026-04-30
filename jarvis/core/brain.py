"""
Jarvis v2.0 — The Brain
=========================
Central reasoning engine that ties together:
  - LLM cascade (Gemini → Groq)
  - Personality layer
  - Context management
  - Cloud sanitization
  - Intent detection

This is the single entry point for ALL Jarvis reasoning.
Other modules call brain.think() — never the LLM directly.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional, AsyncGenerator

from jarvis.config import JarvisConfig
from jarvis.core.llm_provider import LLMCascade, RateLimitError
from jarvis.core.personality import Personality
from jarvis.core.personality import Personality
from jarvis.core.context_manager import ContextManager
from jarvis.security import CloudSanitizer
from jarvis.memory.mempalace_wrapper import JarvisMemory

logger = logging.getLogger("jarvis.brain")


class JarvisBrain:
    """
    The central intelligence of Jarvis.

    All thought goes through here. The Brain:
    1. Takes user input (text or transcribed voice)
    2. Detects intent (question, command, conversation)
    3. Sanitizes sensitive data before cloud calls
    4. Routes to the LLM cascade
    5. Shapes the response through the personality layer
    6. Manages conversation context
    """

    def __init__(self, config: JarvisConfig):
        self.config = config
        self.personality = Personality(
            style=config.personality_style,
            user_name=config.user_name,
        )
        self.context = ContextManager(
            max_messages=20,
            max_tokens=8000,
        )
        self.sanitizer = CloudSanitizer(
            redact_patterns=config.security.redact_patterns,
        )
        self.memory = JarvisMemory()
        self.llm = LLMCascade(config)

        # State tracking
        self._active = True
        self._thinking = False
        self._last_response_time: float = 0
        self._system_state: dict = {}

        logger.info("Jarvis Brain initialized")

    @property
    def is_thinking(self) -> bool:
        return self._thinking

    def update_system_state(self, state: dict):
        """Update the system state context (from monitor)."""
        self._system_state = state

    def _build_system_state_string(self) -> str:
        """Format system state for the LLM context."""
        if not self._system_state:
            return ""

        parts = []
        if "cpu_percent" in self._system_state:
            parts.append(f"CPU: {self._system_state['cpu_percent']}%")
        if "ram_percent" in self._system_state:
            parts.append(f"RAM: {self._system_state['ram_percent']}%")
        if "battery_percent" in self._system_state:
            pct = self._system_state["battery_percent"]
            charging = self._system_state.get("battery_charging", False)
            parts.append(f"Battery: {pct}%{' (charging)' if charging else ''}")
        if "active_window" in self._system_state:
            parts.append(f"Active: {self._system_state['active_window']}")

        return " | ".join(parts) if parts else ""

    async def think(
        self,
        user_input: str,
        temperature: float = None,
        stream: bool = False,
    ) -> str:
        """
        Process user input and generate a response.
        This is the primary entry point for all Jarvis interactions.

        Args:
            user_input: What the user said/typed
            temperature: Override for LLM temperature
            stream: If True, returns an async generator for streaming

        Returns:
            Jarvis's response text
        """
        self._thinking = True
        start_time = time.time()

        try:
            # 1. Add to context
            self.context.add_user_message(user_input)

            # 2. Build the system prompt with personality + context
            now = datetime.now()
            system_prompt = self.personality.get_contextual_prompt(
                current_time=now.strftime("%A, %B %d, %Y %I:%M %p"),
                system_state=self._build_system_state_string(),
            )

            # 3. Sanitize before sending to cloud
            sanitized_input = user_input
            sanitized_history = self.context.get_history()

            if self.config.security.sanitize_before_cloud:
                sanitized_input = self.sanitizer.sanitize(user_input)
                sanitized_history = [
                    {
                        "role": m["role"],
                        "content": self.sanitizer.sanitize(m["content"]),
                    }
                    for m in sanitized_history
                ]
                # Don't sanitize the last message — it's the current input
                if sanitized_history:
                    sanitized_history[-1]["content"] = sanitized_input

            # --- ORCHESTRATOR & MEMORY ROUTING ---
            intent = await self.detect_intent(user_input)
            
            if intent.get("type") == "memory":
                # Handle it directly in the brain using MemPalace
                fact = await self.quick_think(f"Extract the core fact/preference the user wants me to remember from this: '{user_input}'. Output ONLY the fact concisely.")
                await self.memory.store_fact(room="Preferences", drawer="User", item=fact)
                response = self.personality.get_contextual_prompt("", "") # Get base personality
                response = await self.quick_think(f"Acknowledge saving this fact to long-term memory: '{fact}'. Keep it under 15 words and in your Jarvis personality.")
                self.context.add_assistant_message(response, provider="memory")
                self._last_response_time = time.time() - start_time
                return response

            if getattr(self, 'orchestrator', None) and intent.get("type", "conversation") not in ["conversation", "memory"]:
                logger.info(f"Routing intent: {intent}")
                response = await self.orchestrator.route_and_execute(user_input, intent)
                self.context.add_assistant_message(response, provider="agent")
                self._last_response_time = time.time() - start_time
                return response

            # 4. Generate response via LLM cascade
            temp = temperature or self.config.llm.temperature

            response, provider = await self.llm.generate(
                prompt=sanitized_input,
                system_prompt=system_prompt,
                temperature=temp,
                max_tokens=self.config.llm.max_tokens,
                conversation_history=sanitized_history[:-1],  # Exclude current message (it's the prompt)
            )

            # 5. Add response to context
            self.context.add_assistant_message(response, provider=provider)

            elapsed = time.time() - start_time
            self._last_response_time = elapsed
            logger.info(f"Brain response via {provider} in {elapsed:.2f}s ({len(response)} chars)")

            return response

        except RuntimeError as e:
            # All providers failed
            error_response = self.personality.get_error_response("all_providers_down")
            self.context.add_assistant_message(error_response, provider="error")
            logger.error(f"All providers failed: {e}")
            return error_response

        except Exception as e:
            error_response = self.personality.get_error_response("unknown")
            logger.error(f"Brain error: {e}", exc_info=True)
            return error_response

        finally:
            self._thinking = False

    async def think_stream(
        self,
        user_input: str,
        temperature: float = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream a response token by token.
        Used for the HUD to show text appearing in real-time.
        """
        self._thinking = True
        full_response = []

        try:
            self.context.add_user_message(user_input)

            now = datetime.now()
            system_prompt = self.personality.get_contextual_prompt(
                current_time=now.strftime("%A, %B %d, %Y %I:%M %p"),
                system_state=self._build_system_state_string(),
            )

            sanitized_input = user_input
            if self.config.security.sanitize_before_cloud:
                sanitized_input = self.sanitizer.sanitize(user_input)

            temp = temperature or self.config.llm.temperature
            history = self.context.get_history()[:-1]

            async for chunk in self.llm.generate_stream(
                prompt=sanitized_input,
                system_prompt=system_prompt,
                temperature=temp,
                max_tokens=self.config.llm.max_tokens,
                conversation_history=history,
            ):
                full_response.append(chunk)
                yield chunk

            # Add complete response to context
            complete = "".join(full_response)
            self.context.add_assistant_message(complete, provider="stream")

        except Exception as e:
            error_msg = self.personality.get_error_response("unknown")
            yield error_msg
            logger.error(f"Stream error: {e}")

        finally:
            self._thinking = False

    async def quick_think(self, prompt: str, system_override: str = "") -> str:
        """
        Quick one-shot LLM call without context or personality.
        Used internally for things like intent detection, summarization, etc.
        """
        try:
            sanitized = self.sanitizer.sanitize(prompt) if self.config.security.sanitize_before_cloud else prompt
            response, _ = await self.llm.generate(
                prompt=sanitized,
                system_prompt=system_override or "Be concise and direct.",
                temperature=0.3,
                max_tokens=500,
                use_cache=True,
            )
            return response
        except Exception as e:
            logger.error(f"Quick think error: {e}")
            return ""

    async def detect_intent(self, user_input: str) -> dict:
        """
        Classify what the user wants to do.

        Returns dict with:
          - type: "question", "command", "conversation", "search", "code", "system"
          - confidence: float 0-1
          - action: specific action if type is "command"
        """
        intent_prompt = f"""Classify this user input into ONE category.
Input: "{user_input}"

Categories:
- AUTOMATION: User wants to control OS, open desktop apps, volume, settings, workflows
- BROWSER: User specifically asks to do something in a web browser, open a website, play on youtube
- SEARCH: User wants to search the internet/web for factual information
- CODE: User wants help with programming
- SYSTEM: User is asking about their computer's status metrics (CPU, RAM)
- MEMORY: User wants Jarvis to remember, learn, or save a preference/fact for the future.
- CONVERSATION: General chat / not fitting other categories

Reply in EXACTLY this format (no markdown):
TYPE: <category>
ACTION: <specific action or "none">
CONFIDENCE: <0.0 to 1.0>"""

        try:
            response = await self.quick_think(intent_prompt)
            lines = response.strip().split("\n")
            result = {"type": "conversation", "action": "none", "confidence": 0.5}

            for line in lines:
                line = line.strip()
                if line.startswith("TYPE:"):
                    result["type"] = line.split(":", 1)[1].strip().lower()
                elif line.startswith("ACTION:"):
                    result["action"] = line.split(":", 1)[1].strip().lower()
                elif line.startswith("CONFIDENCE:"):
                    try:
                        result["confidence"] = float(line.split(":", 1)[1].strip())
                    except ValueError:
                        pass

            return result

        except Exception as e:
            logger.error(f"Intent detection failed: {e}")
            return {"type": "conversation", "action": "none", "confidence": 0.0}

    def get_greeting(self) -> str:
        """Get a time-appropriate startup greeting."""
        hour = datetime.now().hour
        return self.personality.get_greeting(hour)

    def get_status(self) -> dict:
        """Get brain status for diagnostics."""
        return {
            "active": self._active,
            "thinking": self._thinking,
            "context": self.context.get_stats(),
            "last_response_time": round(self._last_response_time, 2),
            "llm_status": self.llm.status,
            "personality": self.personality.style,
        }

    def new_session(self):
        """Start a fresh conversation session."""
        self.context.clear()
        logger.info("New conversation session started")
