"""
Jarvis v2.0 — Workflow Manager
================================
Executes predefined multi-step YAML workflows and conditional triggers.
Think: "Gaming Mode", "Morning Briefing", "Coding Environment".
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Any

from jarvis.config import WORKFLOWS_DIR

logger = logging.getLogger("jarvis.system.workflows")


class WorkflowManager:
    """Loads and executes predefined automated actions."""

    def __init__(self, commander, os_controller, browser_agent):
        self.commander = commander
        self.oscon = os_controller
        self.browser = browser_agent
        self.workflows: Dict[str, Dict[str, Any]] = {}
        self._create_default_workflows()
        self.load_workflows()

    def _create_default_workflows(self):
        """Create some Iron Man style default workflows if none exist."""
        gaming_mode = {
            "description": "Optimizes system for gaming",
            "steps": [
                {"action": "os_control", "type": "volume", "value": 70},
                {"action": "browser", "type": "close_all_tabs"},
                {"action": "close_app", "target": "chrome"},
                {"action": "launch_app", "target": "steam"},
                {"action": "speak", "text": "Gaming mode engaged. Background processes optimized."}
            ]
        }
        
        coding_mode = {
            "description": "Sets up coding environment",
            "steps": [
                {"action": "launch_app", "target": "vscode"},
                {"action": "browser", "type": "new_tab", "url": "https://stackoverflow.com"},
                {"action": "launch_app", "target": "terminal"},
                {"action": "speak", "text": "Development environment online, Sir."}
            ]
        }
        
        morning_routine = {
            "description": "Starts the day",
            "steps": [
                {"action": "os_control", "type": "volume", "value": 40},
                {"action": "browser", "type": "search_news", "query": "technology"},
                {"action": "speak", "text": "Good morning. I've prepared your daily tech briefing."}
            ]
        }

        # Write to default files safely
        defaults = {"gaming": gaming_mode, "coding": coding_mode, "morning": morning_routine}
        
        for name, data in defaults.items():
            path = WORKFLOWS_DIR / f"{name}.yaml"
            if not path.exists():
                with open(path, "w") as f:
                    yaml.dump(data, f)
                    
    def load_workflows(self):
        """Load all YAML workflows from the workflows directory."""
        self.workflows.clear()
        
        if not WORKFLOWS_DIR.exists():
            return
            
        for filepath in WORKFLOWS_DIR.glob("*.yaml"):
            try:
                with open(filepath, "r") as f:
                    data = yaml.safe_load(f)
                    if data and "steps" in data:
                        name = filepath.stem.lower()
                        self.workflows[name] = data
            except Exception as e:
                logger.error(f"Failed to load workflow {filepath.name}: {e}")
                
        logger.info(f"Loaded {len(self.workflows)} workflows")

    def available_workflows(self) -> List[str]:
        return list(self.workflows.keys())

    async def execute(self, workflow_name: str) -> str:
        """Run a named workflow step-by-step."""
        workflow_name = workflow_name.lower()
        if workflow_name not in self.workflows:
            return f"Workflow '{workflow_name}' not found."

        workflow = self.workflows[workflow_name]
        steps = workflow.get("steps", [])
        
        logger.info(f"Executing workflow: {workflow_name} ({len(steps)} steps)")
        
        results = []
        for i, step in enumerate(steps):
            action = step.get("action")
            
            try:
                if action == "os_control":
                    if step.get("type") == "volume":
                        await self.oscon.set_volume(step.get("value", 50))
                        results.append(f"Set volume to {step.get('value')}")
                    elif step.get("type") == "brightness":
                        await self.oscon.set_brightness(step.get("value", 100))
                        results.append("Adjusted brightness")
                        
                elif action == "launch_app":
                    await self.oscon.open_app(step.get("target"))
                    results.append(f"Launched {step.get('target')}")
                    
                elif action == "close_app":
                    await self.oscon.close_app(step.get("target"))
                    results.append(f"Closed {step.get('target')}")
                    
                elif action == "browser":
                    # Delegate quickly to browser agent
                    if step.get("type") == "close_all_tabs":
                        await self.browser.execute("close all tabs")
                        results.append("Closed browser tabs")
                    elif step.get("type") == "new_tab":
                        url = step.get("url", "")
                        await self.browser.open_url(url)
                        results.append(f"Opened {url}")
                    elif step.get("type") == "search_news":
                        q = step.get("query", "news")
                        await self.browser.search(q, "google")
                        results.append(f"Searched news for '{q}'")
                        
                elif action == "powershell":
                    await self.commander.execute(step.get("command"))
                    results.append(f"Executed PS command")
                    
                elif action == "speak":
                    # Handled externally by returning the text
                    results.append(f"Said: {step.get('text')}")
                    
                # Small delay between actions so we don't overwhelm Windows
                import asyncio
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error in step {i} of {workflow_name}: {e}")
                results.append(f"Error: {e}")
                
        final_speech = next((s.get("text") for s in reversed(steps) if s.get("action") == "speak"), "")
        summary = f"Executed '{workflow_name}'. Steps: {', '.join(results)}"
        
        return summary, final_speech
