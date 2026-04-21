@echo off
setlocal

rem Regenerate VS project files for the Blackjack sample.
rem Requires a UE 5.6 install. Set UE_ROOT to override auto-detection.

if "%UE_ROOT%"=="" (
  echo UE_ROOT not set — using default C:\Program Files\Epic Games\UE_5.6
  set "UE_ROOT=C:\Program Files\Epic Games\UE_5.6"
)

set "UBT=%UE_ROOT%\Engine\Binaries\DotNET\UnrealBuildTool\UnrealBuildTool.exe"
if not exist "%UBT%" (
  echo UnrealBuildTool.exe not found at "%UBT%".
  echo Please set UE_ROOT to your UE 5.6 install root and try again.
  exit /b 1
)

"%UBT%" -projectfiles -project="%~dp0BlackjackSample.uproject" -game -engine -progress
if errorlevel 1 (
  echo Project-file generation failed.
  exit /b 1
)

echo Done. Open BlackjackSample.sln in VS 2022 or Rider.
endlocal
