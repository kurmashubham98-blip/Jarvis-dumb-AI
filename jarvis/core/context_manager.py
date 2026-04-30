"""
Jarvis v2.0 — Context Manager
===============================
Handles conversation history, context windowing, and message management.
Keeps the conversation flowing without exceeding token limits.

Context window strategy:
- Keep the last N messages (configurable, default 20)
- Summarize older messages via LLM when window fills up
- Priority: system prompt > recent messages > summarized history
"""

import time
import logging
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger("jarvis.context")


@dataclass
class Message:
    """A single message in the conversation."""
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: float = field(default_factory=time.time)
    provider: str = ""  # which LLM generated this
    tokens_estimate: int = 0  # rough token count

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}

    def __repr__(self) -> str:
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"Message({self.role}: {preview})"


class ContextManager:
    """
    Manages conversation context with intelligent windowing.

    Ensures we never exceed token limits while maintaining
    coherent conversation flow.
    """

    def __init__(
        self,
        max_messages: int = 20,
        max_tokens: int = 8000,  # Leave room for response
        chars_per_token: float = 4.0,  # Rough estimate
    ):
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self.chars_per_token = chars_per_token

        self._messages: list[Message] = []
        self._summary: str = ""  # Compressed older history
        self._session_start: float = time.time()

    @property
    def message_count(self) -> int:
        return len(self._messages)

    @property
    def session_duration_minutes(self) -> float:
        return (time.time() - self._session_start) / 60

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate (4 chars ≈ 1 token)."""
        return int(len(text) / self.chars_per_token)

    def _total_tokens(self) -> int:
        """Estimate total tokens in current context."""
        total = self._estimate_tokens(self._summary)
        for msg in self._messages:
            total += self._estimate_tokens(msg.content)
        return total

    def add_user_message(self, content: str) -> Message:
        """Add a user message to the context."""
        msg = Message(
            role="user",
            content=content,
            tokens_estimate=self._estimate_tokens(content),
        )
        self._messages.append(msg)
        self._trim_if_needed()
        return msg

    def add_assistant_message(self, content: str, provider: str = "") -> Message:
        """Add a Jarvis response to the context."""
        msg = Message(
            role="assistant",
            content=content,
            provider=provider,
            tokens_estimate=self._estimate_tokens(content),
        )
        self._messages.append(msg)
        self._trim_if_needed()
        return msg

    def get_history(self) -> list[dict]:
        """
        Get conversation history formatted for the LLM.
        Includes summary of older messages if available.
        """
        history = []

        # Prepend summary of older context if available
        if self._summary:
            history.append({
                "role": "user",
                "content": f"[Previous conversation summary: {self._summary}]",
            })
            history.append({
                "role": "assistant",
                "content": "Understood, I have context of our previous conversation.",
            })

        # Add recent messages
        for msg in self._messages:
            history.append(msg.to_dict())

        return history

    def _trim_if_needed(self):
        """Trim messages if we exceed the window."""
        while len(self._messages) > self.max_messages:
            # Move oldest messages to summary
            old = self._messages.pop(0)
            self._update_summary(old)

        # Also trim if token count is too high
        while self._total_tokens() > self.max_tokens and len(self._messages) > 2:
            old = self._messages.pop(0)
            self._update_summary(old)

    def _update_summary(self, old_message: Message):
        """Add an old message to the running summary."""
        role_label = "User" if old_message.role == "user" else "Jarvis"
        preview = old_message.content[:200]  # Keep it brief
        if self._summary:
            self._summary += f" | {role_label}: {preview}"
        else:
            self._summary = f"{role_label}: {preview}"

        # Keep summary from growing too large
        if len(self._summary) > 2000:
            self._summary = self._summary[-1500:]

    def get_last_user_message(self) -> Optional[str]:
        """Get the most recent user message."""
        for msg in reversed(self._messages):
            if msg.role == "user":
                return msg.content
        return None

    def get_last_response(self) -> Optional[str]:
        """Get Jarvis's most recent response."""
        for msg in reversed(self._messages):
            if msg.role == "assistant":
                return msg.content
        return None

    def clear(self):
        """Clear all context (new session)."""
        self._messages.clear()
        self._summary = ""
        self._session_start = time.time()

    def get_stats(self) -> dict:
        """Get context statistics."""
        return {
            "messages": len(self._messages),
            "estimated_tokens": self._total_tokens(),
            "session_minutes": round(self.session_duration_minutes, 1),
            "has_summary": bool(self._summary),
            "summary_length": len(self._summary),
        }
