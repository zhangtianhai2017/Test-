@echo off
setlocal

rem Build the editor target for the Blackjack sample (Win64 Development).

if "%UE_ROOT%"=="" (
  set "UE_ROOT=C:\Program Files\Epic Games\UE_5.6"
)

set "BUILDBAT=%UE_ROOT%\Engine\Build\BatchFiles\Build.bat"
if not exist "%BUILDBAT%" (
  echo Build.bat not found at "%BUILDBAT%".
  echo Please set UE_ROOT to your UE 5.6 install root.
  exit /b 1
)

call "%BUILDBAT%" BlackjackSampleEditor Win64 Development -project="%~dp0BlackjackSample.uproject" -WaitMutex -FromMsBuild
if errorlevel 1 (
  echo Editor build failed.
  exit /b 1
)

echo Editor build complete.
endlocal
