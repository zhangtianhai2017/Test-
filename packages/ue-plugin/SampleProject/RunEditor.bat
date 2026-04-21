@echo off
setlocal

rem Launch the UE 5.6 editor with the Blackjack sample project.

if "%UE_ROOT%"=="" (
  set "UE_ROOT=C:\Program Files\Epic Games\UE_5.6"
)

set "EDITOR=%UE_ROOT%\Engine\Binaries\Win64\UnrealEditor.exe"
if not exist "%EDITOR%" (
  echo UnrealEditor.exe not found at "%EDITOR%".
  echo Please set UE_ROOT to your UE 5.6 install root.
  exit /b 1
)

start "" "%EDITOR%" "%~dp0BlackjackSample.uproject" %*
endlocal
