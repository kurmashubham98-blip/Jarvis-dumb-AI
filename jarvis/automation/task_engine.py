"""
Jarvis v2.0 — Task Engine (Multi-step DAG)
============================================
Allows Jarvis to break complex requests down into a series of steps
that are executed in sequence, passing data between steps if necessary.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Callable, Coroutine

logger = logging.getLogger("jarvis.automation.task_engine")


@dataclass
class TaskStep:
    name: str
    action: Callable[..., Coroutine[Any, Any, Any]]
    kwargs: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    result: Any = None
    status: str = "pending"  # pending, running, success, failed


class TaskDAG:
    """A Directed Acyclic Graph of tasks representing a complex workflow."""
    def __init__(self, name: str):
        self.name = name
        self.steps: Dict[str, TaskStep] = {}
        
    def add_step(self, step: TaskStep):
        self.steps[step.name] = step
        
    async def execute(self) -> Dict[str, Any]:
        """Execute the DAG, respecting dependencies."""
        logger.info(f"Executing complex task: {self.name}")
        
        # Simple execution: we assume a mostly linear sequence for now.
        # A full DAG topological sort is overkill for standard Jarvis tasks,
        # but we do check basic success of previous steps.
        
        overall_results = {}
        
        for name, step in self.steps.items():
            step.status = "running"
            
            # Check dependencies
            can_run = True
            for dep in step.depends_on:
                if dep not in self.steps or self.steps[dep].status != "success":
                    logger.warning(f"Step {name} failed: Dependency {dep} not met.")
                    step.status = "failed"
                    can_run = False
                    break
                    
            if not can_run:
                continue
                
            try:
                # Execute the bound coroutine
                result = await step.action(**step.kwargs)
                step.result = result
                step.status = "success"
                overall_results[name] = result
            except Exception as e:
                logger.error(f"Step {name} failed: {e}")
                step.status = "failed"
                overall_results[name] = {"error": str(e)}
                
        return overall_results
