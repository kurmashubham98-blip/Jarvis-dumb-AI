"""
Jarvis v2.0 — System Monitor
==============================
Continuously tracks system health (CPU, RAM, Disk, Battery, Network, GPU).
Provides data for the Brain's context and Triggers.
"""

import asyncio
import logging
import time
from typing import Dict, Any

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger("jarvis.system.monitor")


class SystemMonitor:
    """Polls system metrics and maintains state."""

    def __init__(self, interval: int = 5):
        self.interval = interval
        self.running = False
        self.current_state: Dict[str, Any] = {
            "cpu_percent": 0.0,
            "ram_percent": 0.0,
            "disk_percent": 0.0,
            "battery_percent": 100,
            "battery_charging": True,
            "idle_minutes": 0,
            "wifi_connected": True,
            "active_window": ""
        }
        self.last_input_time = time.time()

    async def start(self, callback_on_update=None):
        """Start the background monitoring loop."""
        if not psutil:
            logger.error("psutil is not installed. System monitoring disabled.")
            return

        self.running = True
        logger.info("System monitoring started")
        
        while self.running:
            try:
                self._update_metrics()
                if callback_on_update:
                    callback_on_update(self.current_state)
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                
            await asyncio.sleep(self.interval)

    def stop(self):
        """Stop the monitoring loop."""
        self.running = False

    def _update_metrics(self):
        """Poll psutil and Windows APIs for metrics."""
        
        # CPU & RAM
        self.current_state["cpu_percent"] = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        self.current_state["ram_percent"] = mem.percent
        
        # Disk Space (C: drive)
        try:
            disk = psutil.disk_usage('C:\\')
            self.current_state["disk_percent"] = disk.percent
        except:
            pass

        # Battery
        try:
            if hasattr(psutil, "sensors_battery"):
                batt = psutil.sensors_battery()
                if batt:
                    self.current_state["battery_percent"] = batt.percent
                    self.current_state["battery_charging"] = batt.power_plugged
        except:
            pass
            
        # Idle Time (Basic placeholder, needs win32api for real idle time)
        # We simulate this via the Brain tracking last interaction
        pass
        
    def get_state(self) -> Dict[str, Any]:
        """Return the latest system state."""
        return self.current_state.copy()
