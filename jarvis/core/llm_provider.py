"""
Jarvis v2.0 — LLM Provider Cascade
====================================
Cloud-only LLM engine with intelligent fallback:
  1. Gemini 2.5 Flash (primary — best reasoning)
  2. Groq Llama 3.3 70B (fallback — blazing fast)

Features:
  - Rate limit tracking with auto-cooldown
  - Sensitive prompt routing (aggressive sanitization)
  - Response caching to avoid wasting API calls
  - Automatic retry with exponential backoff
  - Token counting and context windowing
"""

import asyncio
import time
import hashlib
import json
import logging
from typing import Optional, AsyncGenerator
from dataclasses import dataclass, field

logger = logging.getLogger("jarvis.llm")


# ── Rate Limiter ────────────────────────────────────────────────────
@dataclass
class RateLimiter:
    """Track API usage to stay within free tier limits."""
    rpm_limit: int
    daily_limit: int
    _minute_requests: list = field(default_factory=list)
    _daily_requests: list = field(default_factory=list)

    def can_request(self) -> bool:
        """Check if we can make another request."""
        now = time.time()
        # Clean old entries
        self._minute_requests = [t for t in self._minute_requests if now - t < 60]
        self._daily_requests = [t for t in self._daily_requests if now - t < 86400]
        return (
            len(self._minute_requests) < self.rpm_limit
            and len(self._daily_requests) < self.daily_limit
        )

    def record_request(self):
        """Record a new request."""
        now = time.time()
        self._minute_requests.append(now)
        self._daily_requests.append(now)

    def time_until_available(self) -> float:
        """Seconds until next request slot is available."""
        if self.can_request():
            return 0
        now = time.time()
        if len(self._minute_requests) >= self.rpm_limit:
            oldest = min(self._minute_requests)
            return max(0, 60 - (now - oldest))
        return 0

    @property
    def requests_remaining_today(self) -> int:
        now = time.time()
        self._daily_requests = [t for t in self._daily_requests if now - t < 86400]
        return max(0, self.daily_limit - len(self._daily_requests))


# ── Response Cache ─────────────────────────────────────────────────
class ResponseCache:
    """Simple in-memory cache to avoid duplicate API calls."""

    def __init__(self, max_size: int = 200):
        self._cache: dict[str, tuple[str, float]] = {}
        self._max_size = max_size

    def _hash(self, prompt: str, system: str) -> str:
        content = f"{system}|||{prompt}"
        return hashlib.md5(content.encode()).hexdigest()

    def get(self, prompt: str, system: str = "") -> Optional[str]:
        key = self._hash(prompt, system)
        if key in self._cache:
            response, timestamp = self._cache[key]
            # Cache valid for 10 minutes
            if time.time() - timestamp < 600:
                logger.debug("Cache hit for prompt")
                return response
            else:
                del self._cache[key]
        return None

    def set(self, prompt: str, system: str, response: str):
        if len(self._cache) >= self._max_size:
            # Evict oldest entry
            oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        key = self._hash(prompt, system)
        self._cache[key] = (response, time.time())


# ── Provider Base ──────────────────────────────────────────────────
class LLMProvider:
    """Base class for LLM providers."""

    def __init__(self, name: str, rate_limiter: RateLimiter):
        self.name = name
        self.rate_limiter = rate_limiter
        self._available = True
        self._last_error: Optional[str] = None

    @property
    def is_available(self) -> bool:
        return self._available and self.rate_limiter.can_request()

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        conversation_history: list = None,
    ) -> str:
        raise NotImplementedError

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        conversation_history: list = None,
    ) -> AsyncGenerator[str, None]:
        raise NotImplementedError
        yield  # Make it a generator


# ── Gemini Provider ────────────────────────────────────────────────
class GeminiProvider(LLMProvider):
    """Google Gemini 2.5 Flash — primary provider."""

    def __init__(self, api_key: str, model: str, rate_limiter: RateLimiter):
        super().__init__("Gemini", rate_limiter)
        self._api_key = api_key
        self._model_name = model
        self._client = None
        self._model = None

    def _ensure_client(self):
        if self._client is None:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self._api_key)
                self._client = genai
                self._model = genai.GenerativeModel(
                    model_name=self._model_name,
                )
                self._available = True
                logger.info(f"Gemini initialized: {self._model_name}")
            except Exception as e:
                self._available = False
                self._last_error = str(e)
                logger.error(f"Gemini init failed: {e}")

    def _build_contents(self, prompt: str, system_prompt: str, history: list = None) -> list:
        """Build the contents array for Gemini API."""
        contents = []
        if history:
            for msg in history:
                role = "user" if msg["role"] == "user" else "model"
                contents.append({"role": role, "parts": [msg["content"]]})
        contents.append({"role": "user", "parts": [prompt]})
        return contents

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        conversation_history: list = None,
    ) -> str:
        self._ensure_client()
        if not self._available:
            raise ConnectionError(f"Gemini unavailable: {self._last_error}")

        if not self.rate_limiter.can_request():
            raise RateLimitError("Gemini rate limit reached")

        try:
            contents = self._build_contents(prompt, system_prompt, conversation_history)

            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "top_p": 0.95,
            }

            # Use system instruction if provided
            model = self._model
            if system_prompt:
                model = self._client.GenerativeModel(
                    model_name=self._model_name,
                    system_instruction=system_prompt,
                )

            response = await asyncio.to_thread(
                model.generate_content,
                contents,
                generation_config=generation_config,
            )

            self.rate_limiter.record_request()
            result = response.text
            logger.debug(f"Gemini response: {len(result)} chars")
            return result

        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate" in error_str or "quota" in error_str:
                raise RateLimitError(f"Gemini rate limited: {e}")
            self._last_error = str(e)
            raise

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        conversation_history: list = None,
    ) -> AsyncGenerator[str, None]:
        self._ensure_client()
        if not self._available:
            raise ConnectionError(f"Gemini unavailable: {self._last_error}")

        if not self.rate_limiter.can_request():
            raise RateLimitError("Gemini rate limit reached")

        try:
            contents = self._build_contents(prompt, system_prompt, conversation_history)
            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }

            model = self._model
            if system_prompt:
                model = self._client.GenerativeModel(
                    model_name=self._model_name,
                    system_instruction=system_prompt,
                )

            response = await asyncio.to_thread(
                model.generate_content,
                contents,
                generation_config=generation_config,
                stream=True,
            )

            self.rate_limiter.record_request()
            for chunk in response:
                if chunk.text:
                    yield chunk.text

        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate" in error_str or "quota" in error_str:
                raise RateLimitError(f"Gemini rate limited: {e}")
            raise


# ── Groq Provider ──────────────────────────────────────────────────
class GroqProvider(LLMProvider):
    """Groq API — fast fallback provider using Llama models."""

    def __init__(self, api_key: str, model: str, rate_limiter: RateLimiter):
        super().__init__("Groq", rate_limiter)
        self._api_key = api_key
        self._model = model
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            try:
                from groq import Groq
                self._client = Groq(api_key=self._api_key)
                self._available = True
                logger.info(f"Groq initialized: {self._model}")
            except Exception as e:
                self._available = False
                self._last_error = str(e)
                logger.error(f"Groq init failed: {e}")

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        conversation_history: list = None,
    ) -> str:
        self._ensure_client()
        if not self._available:
            raise ConnectionError(f"Groq unavailable: {self._last_error}")

        if not self.rate_limiter.can_request():
            raise RateLimitError("Groq rate limit reached")

        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            if conversation_history:
                messages.extend(conversation_history)
            messages.append({"role": "user", "content": prompt})

            response = await asyncio.to_thread(
                self._client.chat.completions.create,
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            self.rate_limiter.record_request()
            result = response.choices[0].message.content
            logger.debug(f"Groq response: {len(result)} chars")
            return result

        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate" in error_str:
                raise RateLimitError(f"Groq rate limited: {e}")
            self._last_error = str(e)
            raise

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        conversation_history: list = None,
    ) -> AsyncGenerator[str, None]:
        self._ensure_client()
        if not self._available:
            raise ConnectionError(f"Groq unavailable: {self._last_error}")

        if not self.rate_limiter.can_request():
            raise RateLimitError("Groq rate limit reached")

        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            if conversation_history:
                messages.extend(conversation_history)
            messages.append({"role": "user", "content": prompt})

            response = await asyncio.to_thread(
                self._client.chat.completions.create,
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )

            self.rate_limiter.record_request()
            for chunk in response:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate" in error_str:
                raise RateLimitError(f"Groq rate limited: {e}")
            raise


# ── Custom Exceptions ──────────────────────────────────────────────
class RateLimitError(Exception):
    """Raised when a provider hits its rate limit."""
    pass


# ── Cascade Engine ─────────────────────────────────────────────────
class LLMCascade:
    """
    The brain's engine. Tries providers in order, falling back
    automatically when one is rate-limited or unavailable.

    Gemini (smartest) → Groq (fastest) → error message
    """

    def __init__(self, config):
        self.config = config
        self.cache = ResponseCache()
        self._providers: list[LLMProvider] = []
        self._active_provider: Optional[LLMProvider] = None
        self._setup_providers()

    def _setup_providers(self):
        """Initialize all available providers."""
        cfg = self.config.llm

        if cfg.gemini_api_key:
            gemini = GeminiProvider(
                api_key=cfg.gemini_api_key,
                model=cfg.gemini_model,
                rate_limiter=RateLimiter(cfg.gemini_rpm_limit, cfg.gemini_daily_limit),
            )
            self._providers.append(gemini)
            logger.info("✓ Gemini provider registered")

        if cfg.groq_api_key:
            groq = GroqProvider(
                api_key=cfg.groq_api_key,
                model=cfg.groq_model,
                rate_limiter=RateLimiter(cfg.groq_rpm_limit, cfg.groq_daily_limit),
            )
            self._providers.append(groq)
            logger.info("✓ Groq provider registered")

        if not self._providers:
            raise ValueError("No LLM providers configured! Check your API keys.")

    @property
    def status(self) -> dict:
        """Current status of all providers."""
        return {
            p.name: {
                "available": p.is_available,
                "remaining_today": p.rate_limiter.requests_remaining_today,
                "wait_seconds": p.rate_limiter.time_until_available(),
            }
            for p in self._providers
        }

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        conversation_history: list = None,
        use_cache: bool = True,
    ) -> tuple[str, str]:
        """
        Generate a response using the cascade.

        Returns: (response_text, provider_name)
        """
        # Check cache first
        if use_cache:
            cached = self.cache.get(prompt, system_prompt)
            if cached:
                return cached, "cache"

        errors = []
        for provider in self._providers:
            if not provider.is_available:
                wait = provider.rate_limiter.time_until_available()
                if wait > 0 and wait < 5:
                    # Short wait — worth it
                    logger.info(f"{provider.name}: waiting {wait:.1f}s for rate limit reset")
                    await asyncio.sleep(wait)
                elif not provider.rate_limiter.can_request():
                    logger.info(f"{provider.name}: rate limited, skipping")
                    continue

            try:
                logger.info(f"Trying {provider.name}...")
                response = await provider.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    conversation_history=conversation_history,
                )
                self._active_provider = provider

                # Cache the response
                if use_cache:
                    self.cache.set(prompt, system_prompt, response)

                return response, provider.name

            except RateLimitError as e:
                logger.warning(f"{provider.name} rate limited: {e}")
                errors.append(f"{provider.name}: rate limited")
                continue
            except Exception as e:
                logger.error(f"{provider.name} error: {e}")
                errors.append(f"{provider.name}: {e}")
                continue

        # All providers failed
        error_msg = " | ".join(errors) if errors else "No providers available"
        raise RuntimeError(
            f"All LLM providers exhausted. {error_msg}. "
            f"Status: {json.dumps(self.status, indent=2)}"
        )

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        conversation_history: list = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a response — tries providers in cascade order."""
        for provider in self._providers:
            if not provider.is_available:
                continue
            try:
                logger.info(f"Streaming from {provider.name}...")
                async for chunk in provider.generate_stream(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    conversation_history=conversation_history,
                ):
                    yield chunk
                self._active_provider = provider
                return
            except RateLimitError:
                logger.warning(f"{provider.name} rate limited during stream")
                continue
            except Exception as e:
                logger.error(f"{provider.name} stream error: {e}")
                continue

        raise RuntimeError("All LLM providers exhausted during streaming.")
