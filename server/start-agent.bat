@echo off
setlocal

REM start-agent.bat - double-click to launch the relay agent.
REM
REM Edit the two SET lines below to your values, then save and run.
REM Pure ASCII only - do not save this file as UTF-8 with BOM or UTF-16.
REM Notepad's default ANSI encoding is fine; VS Code: bottom right
REM corner -> change encoding to "Save with Encoding: Windows 1252"
REM or "GB2312".

set "RELAY_URL=http://YOUR-SERVER/relay.jsp"
set "AGENT_TOKEN=PASTE-AGENT-TOKEN-HERE"

REM Working directory passed to executed scripts. Default: parent of this .bat.
cd /d "%~dp0\.."

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0agent.ps1"

pause
endlocal
