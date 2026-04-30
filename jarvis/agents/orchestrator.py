"""
Jarvis v2.0 — Orchestrator (Agent Router)
===========================================
Decides WHICH specialist agent should handle a query,
or handles it directly if it's a general question.
"""

import logging
from typing import Dict, Any, List

from jarvis.agents.base import BaseAgent

logger = logging.getLogger("jarvis.agents.orchestrator")


class Orchestrator:
    """Routes queries to the appropriate sub-agent."""

    def __init__(self, brain):
        self.brain = brain
        self.agents: Dict[str, BaseAgent] = {}
        
    def register_agent(self, agent: BaseAgent):
        """Add an agent to the orchestrator."""
        self.agents[agent.name.lower()] = agent
        logger.info(f"Registered agent: {agent.name}")

    async def route_and_execute(self, query: str, intent: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        """
        Determine the right agent and execute.
        If no specific agent is needed, use the main Brain.
        """
        intent_type = intent.get("type", "conversation")
        
        # Mapping intents to agent names
        routing_map = {
            "code": "coding",
            "search": "research",
            "browser": "browser", 
            "system": "automation",
            "automation": "automation"
        }
        
        target_agent_name = routing_map.get(intent_type)
        
        if target_agent_name and target_agent_name in self.agents:
            agent = self.agents[target_agent_name]
            logger.info(f"Routing '{query[:30]}...' to {agent.name} Agent")
            
            try:
                # Let the specialist agent handle it
                return await agent.process(query, context)
            except Exception as e:
                logger.error(f"Agent {agent.name} failed: {e}")
                return f"My {agent.name} sub-system encountered an error: {e}"
        
        # Fallback to general Brain LLM
        return await self.brain.think(query)

    def get_status(self) -> dict:
        return {
            "registered_agents": list(self.agents.keys())
        }
