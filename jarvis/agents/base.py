"""
Jarvis v2.0 — Base Agent
==========================
Defines the common interface for all specialist agents.
"""

import logging
from typing import Any, Dict

class BaseAgent:
    """Base class for all Jarvis sub-agents."""
    
    def __init__(self, name: str, description: str, brain):
        self.name = name
        self.description = description
        self.brain = brain
        self.logger = logging.getLogger(f"jarvis.agents.{name.lower().replace(' ', '_')}")
        
    async def process(self, query: str, context: Dict[str, Any] = None) -> str:
        """
        Process a user request specifically tailored for this agent.
        Must be implemented by subclasses.
        """
        raise NotImplementedError
