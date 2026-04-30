"""
Jarvis v2.0 — Coding Agent
============================
Specialist agent for programming tasks.
Provides deeper focus on technical accuracy, syntax, and debugging.
"""

from typing import Dict, Any

from jarvis.agents.base import BaseAgent


class CodingAgent(BaseAgent):
    """Agent specialized in writing code and debugging."""
    
    def __init__(self, brain):
        super().__init__("Coding", "Specialist for programming, script generation, and debugging", brain)
        
        # Override the system prompt for coding tasks
        self.coding_system_prompt = """You are Jarvis's sub-routine dedicated to programming.
Your task is to write clean, secure, and highly optimized code.
- Provide ONLY code and very brief explanations.
- If writing Python, ensure PEP8 compliance.
- Explain Big-O complexity if applicable.
- If debugging, point out the exact line and explain the fix."""
        
    async def process(self, query: str, context: Dict[str, Any] = None) -> str:
        self.logger.info(f"Processing coding request: {query[:30]}...")
        
        # We bypass the normal personality layer and use a strict technical prompt
        # We can use the brain's quick_think which allows a system_override
        response = await self.brain.quick_think(query, system_override=self.coding_system_prompt)
        
        return response
