"""
Jarvis v2.0 — Research Agent
==============================
Specialized in gathering information using the Research Engine,
synthesizing data, and presenting it clearly.
"""

from typing import Dict, Any

from jarvis.agents.base import BaseAgent
from jarvis.system.research import ResearchEngine


class ResearchAgent(BaseAgent):
    """Agent specialized in web search and synthesis."""
    
    def __init__(self, brain):
        super().__init__("Research", "Specialist for web search, news gathering, and data synthesis", brain)
        self.research_engine = ResearchEngine()
        
    async def process(self, query: str, context: Dict[str, Any] = None) -> str:
        self.logger.info(f"Processing research request: {query[:30]}...")
        
        # Extract the core search topic
        topic_extract_prompt = f"Extract the core search topic from this request: '{query}'. Return ONLY the raw search string."
        topic = await self.brain.quick_think(topic_extract_prompt, system_override="Be incredibly concise. 1-5 words max.")
        
        # Perform the actual internet search
        self.logger.info(f"Detected topic: {topic}. Initiating DuckDuckGo search.")
        search_data = await self.research_engine.search(topic, max_results=4)
        
        # Synthesize the results using standard Jarvis personality
        synthesis_prompt = f"""The user asked: "{query}"

I have retrieved the following web search data:
{search_data}

Please synthesize this into a clear, concise, and helpful answer."""

        response = await self.brain.think(synthesis_prompt)
        return response
