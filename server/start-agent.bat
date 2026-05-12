@echo off
REM start-agent.bat — double-click to launch the relay agent.
REM
REM Edit the two values below once, then double-click this file.
REM Logs go to .\agent.log in this directory.
REM
REM No admin needed. Uses -ExecutionPolicy Bypass at invoke time so
REM the system policy doesn't block agent.ps1.

set RELAY_URL=http://YOUR-SERVER/relay.jsp
set AGENT_TOKEN=PASTE-AGENT-TOKEN-HERE

REM Optional: change working dir (default = this batch's dir).
cd /d "%~dp0\.."

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0agent.ps1"

REM If the agent ever exits cleanly, pause so you can read the last line.
pause
