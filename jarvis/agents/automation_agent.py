"""
Jarvis v2.0 — Automation Agent
================================
Specialized in interacting with system controllers and workflows.
"""

from typing import Dict, Any

from jarvis.agents.base import BaseAgent


class AutomationAgent(BaseAgent):
    """Agent specialized in invoking OS controls and workflows."""
    
    def __init__(self, brain, oscon, commander, workflow_mgr):
        super().__init__("Automation", "Specialist for OS control, file system, and workflows", brain)
        self.oscon = oscon
        self.commander = commander
        self.workflow = workflow_mgr
        
    async def process(self, query: str, context: Dict[str, Any] = None) -> str:
        self.logger.info(f"Processing automation request: {query[:30]}...")
        
        # We ask the LLM to map the query to a specific automation action
        mapping_prompt = f"""Map the following user request to an automation action.
Request: "{query}"

Available actions (Return exactly one of these strings):
- launch_app:<app_name> (if they want to open an app)
- close_app:<app_name> (if they want to close an app)
- volume:<up/down/mute/number> (if they want to change volume)
- wifi:<on/off> (if they want to toggle wifi)
- workflow:<name> (if it matches an established routine)
- unknown (if you cannot map it)

Return ONLY the single action string."""

        action_str = await self.brain.quick_think(mapping_prompt)
        action_str = action_str.strip().lower()
        
        self.logger.info(f"Mapped action: {action_str}")
        
        if action_str.startswith("launch_app:"):
            app = action_str.split(":")[1]
            success = await self.oscon.open_app(app)
            return f"Opening {app}, Sir." if success else f"I was unable to open {app}."
            
        elif action_str.startswith("close_app:"):
            app = action_str.split(":")[1]
            success = await self.oscon.close_app(app)
            return f"Closed {app}." if success else f"I couldn't close {app}."
            
        elif action_str.startswith("volume:"):
            val = action_str.split(":")[1]
            if val == "mute":
                await self.oscon.mute_volume()
                return "System muted."
            else:
                # Basic mapping, a true system would have more granular control
                await self.oscon.set_volume(50) 
                return "Adjusting volume."
                
        elif action_str.startswith("workflow:"):
            wf = action_str.split(":")[1]
            result = await self.workflow.execute(wf)
            if isinstance(result, tuple):
                res, text = result
                return text if text else res
            return str(result)
            
        return "I understand you want to automate something, but I lack the specific integration for that command yet."
