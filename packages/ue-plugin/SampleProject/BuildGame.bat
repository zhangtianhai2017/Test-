@echo off
setlocal

rem Package a Win64 Shipping build via UAT's BuildCookRun workflow.

if "%UE_ROOT%"=="" (
  set "UE_ROOT=C:\Program Files\Epic Games\UE_5.6"
)

set "UAT=%UE_ROOT%\Engine\Build\BatchFiles\RunUAT.bat"
if not exist "%UAT%" (
  echo RunUAT.bat not found at "%UAT%".
  echo Please set UE_ROOT to your UE 5.6 install root.
  exit /b 1
)

set "ARCHIVE=%~dp0Saved\StagedBuilds"
if not exist "%ARCHIVE%" mkdir "%ARCHIVE%"

call "%UAT%" BuildCookRun ^
  -project="%~dp0BlackjackSample.uproject" ^
  -noP4 -platform=Win64 -clientconfig=Shipping -serverconfig=Shipping ^
  -cook -allmaps -build -stage -pak -archive ^
  -archivedirectory="%ARCHIVE%" ^
  -utf8output
if errorlevel 1 (
  echo Game packaging failed.
  exit /b 1
)

echo Shipping package available under "%ARCHIVE%".
endlocal
