"""
Jarvis v2.0 — Trigger Engine
==============================
Monitors system state and triggers automated actions based on
configured rules. Examples: Low battery → power saver, High CPU → clear RAM.
"""

import logging
import time
from typing import Dict, Any, Callable

# Simple dict to provide variables for the eval() sandbox
import math
import operator

from jarvis.config import TriggerRule

logger = logging.getLogger("jarvis.automation.triggers")


class TriggerEngine:
    """Evaluates rules against system state to trigger autonomous actions."""

    def __init__(self, rules: list[TriggerRule], action_callback: Callable):
        self.rules = rules
        self.action_callback = action_callback
        self.last_triggered: Dict[str, float] = {}
        
        # Variables we inject into the condition evaluation context
        self.safe_globals = {
            "math": math,
            "operator": operator,
            "__builtins__": {}  # Lock down __builtins__
        }

    def evaluate_state(self, state: Dict[str, Any]):
        """
        Evaluate all enabled rules against current system state.
        
        Args:
            state: Dictionary containing system metrics (cpu, battery, time, etc.)
        """
        now = time.time()
        
        # Add derived timeframe variables to state for ease of use
        import datetime
        dt = datetime.datetime.now()
        eval_state = state.copy()
        eval_state["time_hour"] = dt.hour
        eval_state["time_minute"] = dt.minute
        
        for rule in self.rules:
            if not rule.enabled:
                continue
                
            # Check cooldown
            last_run = self.last_triggered.get(rule.name, 0)
            if now - last_run < rule.cooldown_seconds:
                continue
                
            try:
                # Safe evaluation of the condition string using the provided state var
                # This requires careful construction in the config
                # E.g., rule.condition = "battery_percent < 20 and charging == False"
                
                # Combine safe environment with state variables
                env = self.safe_globals.copy()
                env.update(eval_state)
                
                # Evaluate the condition
                condition_met = eval(rule.condition, env)
                
                if condition_met:
                    logger.info(f"Trigger condition met: {rule.name}")
                    self.last_triggered[rule.name] = now
                    
                    # Format message if it contains variables
                    msg = rule.message
                    if msg:
                        try:
                            msg = msg.format(**eval_state)
                        except KeyError:
                            pass # Formatting string missing key, use raw
                            
                    # Fire action via the callback
                    import asyncio
                    asyncio.create_task(self.action_callback(rule.action, msg))
                    
            except Exception as e:
                # E.g., variable missing from state during polling (normal)
                if not isinstance(e, NameError):
                    logger.error(f"Error evaluating rule '{rule.name}': {e}")
