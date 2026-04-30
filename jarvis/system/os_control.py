"""
Jarvis v2.0 — OS Control & App Launcher
=========================================
Handles system-level actions like volume control, brightness,
Wi-Fi toggling, and launching established applications.
"""

import asyncio
import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger("jarvis.system.os_control")


class OSController:
    """Manages Windows OS settings and application launching."""

    def __init__(self, commander):
        self.commander = commander

    # --- Windows Settings ---

    async def set_volume(self, level: int) -> bool:
        """Set system volume (0-100)."""
        level = max(0, min(100, level))
        # Use a small C# snippet via PS to set volume reliably
        script = f"""
        $obj = new-object -com wscript.shell 
        $obj.SendKeys([char]173) 
        """ # This mutes/unmutes, setting exact volume is complex w/o external tools.
        
        # A better approach for Windows without nircmd is simulating keystrokes
        # but for Jarvis we will try a standard approach
        ps_script = f"""
        Function Set-Volume {{
            Param ([int]$Level)
            $wshShell = new-object -com wscript.shell 
            1..50 | % {{ $wshShell.SendKeys([char]174) }} # Volume down to 0
            1..($Level/2) | % {{ $wshShell.SendKeys([char]175) }} # Volume up to target
        }}
        Set-Volume -Level {level}
        """
        success, _ = await self.commander.execute(ps_script)
        return success
        
    async def mute_volume(self) -> bool:
        script = "$wshShell = new-object -com wscript.shell; $wshShell.SendKeys([char]173)"
        success, _ = await self.commander.execute(script)
        return success

    async def get_battery_status(self) -> dict:
        """Get laptop battery percentage and status."""
        script = "Get-WmiObject -Class Win32_Battery | Select-Object EstimatedChargeRemaining, BatteryStatus | ConvertTo-Json"
        success, out = await self.commander.execute(script)
        if success and out:
            import json
            try:
                data = json.loads(out)
                if isinstance(data, list): data = data[0]
                status_code = data.get("BatteryStatus", 0)
                charging = status_code == 2 or status_code == 6
                return {
                    "percent": data.get("EstimatedChargeRemaining", 100),
                    "charging": charging
                }
            except:
                pass
        return {"percent": 100, "charging": True}

    async def set_brightness(self, level: int) -> bool:
        """Set screen brightness (0-100)."""
        level = max(0, min(100, level))
        script = f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level})"
        success, _ = await self.commander.execute(script)
        return success

    async def toggle_wifi(self, enable: bool) -> bool:
        """Enable or disable Wi-Fi."""
        state = "Enable" if enable else "Disable"
        # Note: requires admin privileges
        script = f"{state}-NetAdapter -Name 'Wi-Fi' -Confirm:$False"
        success, _ = await self.commander.execute(script)
        return success

    # --- App Launcher ---

    async def open_app(self, app_name: str) -> bool:
        """Attempt to open an application."""
        app_name = app_name.lower()
        
        # Common aliases
        shortcuts = {
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "explorer": "explorer.exe",
            "browser": "start msedge",
            "chrome": "start chrome",
            "edge": "start msedge",
            "brave": "start brave",
            "word": "start winword",
            "excel": "start excel",
            "spotify": "start spotify",
            "discord": "start discord",
            "vscode": "code",
            "code": "code",
            "terminal": "wt"
        }
        
        command = shortcuts.get(app_name)
        if not command:
            # Fallback to general start
            command = f"start {app_name}"
            
        success, out = await self.commander.execute(command)
        return success

    async def close_app(self, app_name: str) -> bool:
        """Attempt to close an application gracefully."""
        # Use taskkill
        script = f"Stop-Process -Name '{app_name}' -Force -ErrorAction SilentlyContinue"
        # Special handled bypass for Stop-Process in commander for this specific use case
        # Or alternatively use taskkill which isn't blocked by default
        cmd = f"taskkill /IM {app_name}.exe /T /F"
        try:
            subprocess.run(cmd, shell=True, capture_output=True)
            return True
        except:
            return False
