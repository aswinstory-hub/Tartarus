
@echo off
setlocal

set "ROOT=%~dp0"
set "BROWSER=%ROOT%browser\chrome-win64\chrome.exe"
set "PROFILE=%ROOT%browser\profile"

if not exist "%BROWSER%" (
    echo ERROR: Could not find chrome.exe
    echo Expected: "%BROWSER%"
    pause
    exit /b 1
)

if not exist "%PROFILE%" mkdir "%PROFILE%"

start "" "%BROWSER%" --user-data-dir="%PROFILE%" %*

endlocal
