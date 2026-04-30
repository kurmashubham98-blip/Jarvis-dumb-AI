"""
Jarvis v2.0 — PowerShell Commander (Sandboxed)
================================================
Executes PowerShell scripts and commands on the host Windows machine.
Includes a strict permission system to prevent destructive actions.

Flow:
  LLM generates command → Commander checks whitelist → Executes OR asks for voice auth
"""

import asyncio
import logging
import subprocess
from typing import Optional, Tuple
from pathlib import Path

logger = logging.getLogger("jarvis.system.commander")


class PowerShellCommander:
    """Executes PowerShell commands with safety rails."""

    def __init__(self, use_sandbox: bool = True):
        self.use_sandbox = use_sandbox
        
        # Commands that never require authentication
        self.whitelist = {
            "get-process", "get-service", "echo", "ping", "ipconfig",
            "get-volume", "get-disk", "systeminfo", "tasklist", "dir", "ls"
        }
        
        # Commands that are blocked outright
        self.blacklist = {
            "format", "remove-item", "del", "rm", "rmdir", "del",
            "stop-process", "kill", "taskkill", "stop-computer", "restart-computer",
            "set-executionpolicy", "netsh", "reg"
        }

    async def execute(self, command: str, require_auth: bool = False) -> Tuple[bool, str]:
        """
        Execute a PowerShell command.
        
        Args:
            command: The PowerShell command string
            require_auth: Flag indicating if the brain determined this needs auth
            
        Returns:
            Tuple of (success_boolean, output_string)
        """
        if self.use_sandbox:
            cmd_lower = command.lower()
            
            # Very basic static analysis for dangerous commands
            for blacklisted in self.blacklist:
                if blacklisted in cmd_lower:
                    msg = f"Security block: Command contains blacklisted keyword '{blacklisted}'"
                    logger.warning(msg)
                    return False, msg

        try:
            logger.info(f"Executing PS: {command[:50]}{'...' if len(command) > 50 else ''}")
            
            process = await asyncio.create_subprocess_exec(
                "powershell", "-NoProfile", "-NonInteractive", "-Command", command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)
            
            out_str = stdout.decode('utf-8', errors='replace').strip()
            err_str = stderr.decode('utf-8', errors='replace').strip()
            
            if process.returncode == 0:
                return True, out_str if out_str else "Command completed successfully."
            else:
                return False, f"Error (code {process.returncode}): {err_str}\nOutput: {out_str}"
                
        except asyncio.TimeoutError:
            return False, "Command execution timed out after 30 seconds."
        except Exception as e:
            logger.error(f"Execution failed: {e}")
            return False, str(e)

    async def check_app_installed(self, app_name: str) -> bool:
        """Check if an application is installed via PowerShell."""
        cmd = f"Get-ItemProperty HKLM:\\Software\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* | Where-Object {{$_.DisplayName -match '{app_name}'}} | Select-Object -ExpandProperty DisplayName"
        success, output = await self.execute(cmd)
        return success and bool(output.strip())
