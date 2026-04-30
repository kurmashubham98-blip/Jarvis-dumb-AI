@echo off
title SHUTDOWN PROTOCOL
color 0c
echo ==============================================
echo        J.A.R.V.I.S TERMINATION SEQUENCE
echo ==============================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$found = $false; $processes = Get-CimInstance Win32_Process; foreach ($p in $processes) { if ($p.Name -match 'python\.exe|pythonw\.exe|cmd\.exe|wscript\.exe|conhost\.exe') { if ($p.CommandLine -match '(?i)jarvis' -and $p.CommandLine -notmatch '(?i)Kill_Jarvis') { if (-not $found) { Write-Host ' [!] Jarvis background presence detected. Engaging termination...' -ForegroundColor Yellow; $found = $true }; Write-Host \"     -^> Purging PID $($p.ProcessId) [$($p.Name)]\" -ForegroundColor Red; Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue } } }; if (-not $found) { Write-Host ' [i] No active Jarvis subsystems found. System is already clear.' -ForegroundColor Green } else { Write-Host ' [~] All Jarvis tasks have been successfully purged.' -ForegroundColor Green }"

echo.
echo  Goodbye, Sir.
echo.
timeout /t 3 >nul
