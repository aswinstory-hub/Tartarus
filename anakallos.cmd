
@echo off
setlocal

:: Root directory (Tartarus)
set "ROOT=%~dp0"

:: Python sandbox (Phylax)
set "SANDBOX=%ROOT%Phylax"

:: Portable Helix directory
set "HELIX=%ROOT%Kallos"

:: Verify Helix executable
if not exist "%HELIX%\hx.exe" (
    echo ERROR: Helix executable not found: "%HELIX%\hx.exe"
    exit /b 1
)

:: Verify Helix runtime
if not exist "%HELIX%\runtime" (
    echo ERROR: Helix runtime folder not found.
    exit /b 1
)

:: Verify Phylax project
if not exist "%SANDBOX%\pyproject.toml" (
    echo ERROR: Phylax pyproject.toml not found.
    exit /b 1
)

:: Configure Helix runtime
set "HELIX_RUNTIME=%HELIX%\runtime"

:: Add Helix to PATH for this session
set "PATH=%HELIX%;%PATH%"

:: Change working directory to Phylax
cd /d "%SANDBOX%"

:: Launch Helix
"%HELIX%\hx.exe" %*

endlocal
