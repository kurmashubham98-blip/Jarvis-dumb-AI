"""
Jarvis v2.0 — Cloud Sanitizer
===============================
Strips sensitive information from prompts BEFORE they leave your machine.
This is critical since we're using free cloud APIs that may log/use your data.

Sanitization strategy:
1. Regex-based PII detection (emails, phone numbers, passwords)
2. Path anonymization (replaces user-specific paths)
3. API key/token detection and redaction
4. Custom blocklist patterns
"""

import re
import logging
from typing import Optional

logger = logging.getLogger("jarvis.security")


class CloudSanitizer:
    """
    Strips sensitive data from text before sending to cloud APIs.
    Think of this as a privacy firewall for your prompts.
    """

    def __init__(self, redact_patterns: list = None, user_name: str = ""):
        self._user_name = user_name or self._detect_username()
        self._patterns = self._build_patterns(redact_patterns or [])

    @staticmethod
    def _detect_username() -> str:
        """Detect the current Windows username for path sanitization."""
        import os
        return os.getenv("USERNAME", os.getenv("USER", "user"))

    def _build_patterns(self, extra_patterns: list) -> list:
        """Build the full set of regex patterns for sanitization."""
        patterns = [
            # Email addresses
            (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "[EMAIL_REDACTED]"),

            # Phone numbers (various formats)
            (r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", "[PHONE_REDACTED]"),
            (r"\+\d{1,3}\s?\d{4,14}", "[PHONE_REDACTED]"),

            # Passwords in various formats
            (r"(?i)(?:password|passwd|pwd)\s*[:=]\s*\S+", "password=[REDACTED]"),

            # API keys/tokens (generic patterns)
            (r"(?i)(?:api[_-]?key|token|secret|auth)\s*[:=]\s*['\"]?\S{20,}['\"]?", "[API_KEY_REDACTED]"),

            # Bearer tokens
            (r"(?i)Bearer\s+[A-Za-z0-9\-._~+/]+=*", "Bearer [TOKEN_REDACTED]"),

            # AWS-style keys
            (r"(?:AKIA|ASIA)[A-Z0-9]{16}", "[AWS_KEY_REDACTED]"),

            # Generic hex secrets (32+ chars)
            (r"\b[0-9a-fA-F]{32,}\b", "[HEX_SECRET_REDACTED]"),

            # SSH private keys
            (r"-----BEGIN (?:RSA |DSA |EC )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |DSA |EC )?PRIVATE KEY-----",
             "[PRIVATE_KEY_REDACTED]"),

            # Windows user paths → anonymized
            (rf"[A-Za-z]:\\\\Users\\\\{re.escape(self._user_name)}", r"C:\\Users\\[USER]"),
            (r"[A-Za-z]:\\\\Users\\\\[^\\\s]+", r"C:\\Users\\[USER]"),

            # Home dir references
            (r"~\/", r"[HOME]/"),

            # IP addresses (private ranges preserved, public redacted)
            (r"\b(?!192\.168\.)(?!10\.)(?!172\.(?:1[6-9]|2\d|3[01])\.)(?:\d{1,3}\.){3}\d{1,3}\b",
             "[IP_REDACTED]"),

            # Credit card numbers (basic)
            (r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "[CARD_REDACTED]"),

            # SSN
            (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN_REDACTED]"),
        ]

        # Add custom patterns
        for pattern in extra_patterns:
            if isinstance(pattern, str):
                patterns.append((pattern, "[REDACTED]"))
            elif isinstance(pattern, (list, tuple)) and len(pattern) == 2:
                patterns.append(tuple(pattern))

        return patterns

    def sanitize(self, text: str) -> str:
        """
        Sanitize text by removing/replacing sensitive information.

        Args:
            text: Raw text that may contain sensitive data.

        Returns:
            Sanitized text safe for cloud API transmission.
        """
        if not text:
            return text

        sanitized = text

        for pattern, replacement in self._patterns:
            try:
                sanitized = re.sub(pattern, replacement, sanitized)
            except re.error as e:
                logger.warning(f"Regex error with pattern {pattern[:30]}...: {e}")

        return sanitized

    def is_sensitive(self, text: str) -> bool:
        """Check if text contains any sensitive patterns."""
        for pattern, _ in self._patterns:
            try:
                if re.search(pattern, text):
                    return True
            except re.error:
                continue
        return False

    def get_sensitivity_report(self, text: str) -> dict:
        """Get a detailed report of what sensitive data was found."""
        findings = []
        for pattern, replacement in self._patterns:
            try:
                matches = re.findall(pattern, text)
                if matches:
                    findings.append({
                        "type": replacement.strip("[]"),
                        "count": len(matches),
                        "pattern": pattern[:40] + "...",
                    })
            except re.error:
                continue

        return {
            "is_sensitive": len(findings) > 0,
            "findings": findings,
            "total_detections": sum(f["count"] for f in findings),
        }
