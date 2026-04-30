"""
Jarvis v2.0 — Security Agent (Permissions & Auth)
===================================================
Handles Voice passphrases and blocking destructive operations.
"""

import logging
from typing import Tuple

logger = logging.getLogger("jarvis.security.auth")


class SecurityAgent:
    """Manages permissions and authentication for sensitive actions."""

    def __init__(self, config):
        self.config = config
        self.voice_passphrase = config.security.voice_passphrase.lower()
        self.authenticated = False
        
    def check_permission(self, action: str, target: str) -> Tuple[bool, str]:
        """
        Check if an action is allowed.
        Returns: Tuple(is_allowed, reason_msg)
        """
        target_lower = target.lower()
        
        # Check blocked paths
        for blocked in self.config.security.blocked_paths:
            # Simple wildcard matching
            if blocked.replace('*', '').lower() in target_lower:
                logger.warning(f"Security block: Attempted access to protected path {target}")
                return False, f"Access to {target} is blocked by security protocol."
                
        return True, "Allowed"

    def verify_voice_auth(self, spoken_text: str) -> bool:
        """Check if the user spoke the authorization passphrase."""
        if not self.voice_passphrase:
            return True # If no passphrase set, everything is authorized
            
        # Example passphrase: "gamma protocol delta"
        if self.voice_passphrase in spoken_text.lower():
            self.authenticated = True
            logger.info("Voice authentication SUCCESS")
            return True
            
        return False
        
    def revoke_auth(self):
        """Revoke temporary authentication."""
        self.authenticated = False
