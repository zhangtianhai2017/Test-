@echo off
setlocal

rem Launch the packaged Win64 Shipping game produced by BuildGame.bat.

set "STAGED=%~dp0Saved\StagedBuilds\Windows\BlackjackSample.exe"
if not exist "%STAGED%" (
  set "STAGED=%~dp0Saved\StagedBuilds\WindowsNoEditor\BlackjackSample.exe"
)
if not exist "%STAGED%" (
  echo Packaged build not found. Run BuildGame.bat first.
  exit /b 1
)

start "" "%STAGED%" %*
endlocal
