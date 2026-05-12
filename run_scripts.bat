@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "PYTHON_INSTALLER=installer\python-3.12.10-amd64.exe"
set "UV_ZIP=installer\uv-x86_64-pc-windows-msvc.zip"
set "UV_DIR=installer\uv"
set "UV_EXE=%UV_DIR%\uv.exe"
set "WHEELS_DIR=installer\wheels"
set "REQUIREMENTS=installer\requirements.txt"

echo ============================================================
echo   KUKA EIP Monitoring - One-click launcher
echo ============================================================

:: ── 1. Verify required installer files ────────────────────
if not exist "%PYTHON_INSTALLER%" (
    echo [ERROR] Missing: %PYTHON_INSTALLER%
    pause & exit /b 1
)
if not exist "%UV_ZIP%" (
    echo [ERROR] Missing: %UV_ZIP%
    pause & exit /b 1
)

:: ── 2. Check Python ───────────────────────────────────────
echo [CHECK] Python...
set "PY_EXE="
where python >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=2" %%V in ('python --version 2^>^&1') do set "PY_VER=%%V"
    echo !PY_VER! | findstr /b "3.12" >nul
    if not errorlevel 1 set "PY_EXE=python"
)
if not defined PY_EXE if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)

if not defined PY_EXE (
    echo [SETUP] Python 3.12 not found. Installing offline...
    "%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1
    if errorlevel 1 (
        echo [ERROR] Python install failed.
        pause & exit /b 1
    )
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set "PY_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    ) else (
        echo.
        echo [INFO] Python installed. Please CLOSE this window and re-run run_scripts.bat
        pause & exit /b 0
    )
)
echo [OK]    Python: !PY_EXE!

:: ── 3. Extract uv ─────────────────────────────────────────
if not exist "%UV_EXE%" (
    echo [SETUP] Extracting uv...
    if not exist "%UV_DIR%" mkdir "%UV_DIR%"
    powershell -NoProfile -Command "Expand-Archive -Path '%UV_ZIP%' -DestinationPath '%UV_DIR%' -Force"
    if not exist "%UV_EXE%" (
        echo [ERROR] uv extraction failed.
        pause & exit /b 1
    )
)
echo [OK]    uv ready.

:: ── 4. Create venv + offline install ──────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo [SETUP] Creating .venv with Python 3.12...
    "%UV_EXE%" venv --python "!PY_EXE!" .venv
    if errorlevel 1 (
        echo [ERROR] uv venv failed.
        pause & exit /b 1
    )
    echo [SETUP] Installing dependencies offline from %WHEELS_DIR%...
    "%UV_EXE%" pip install --python ".venv\Scripts\python.exe" --no-index --find-links "%WHEELS_DIR%" -r "%REQUIREMENTS%"
    if errorlevel 1 (
        echo [ERROR] Offline install failed.
        pause & exit /b 1
    )
)
echo [OK]    .venv ready.

:: ── 6. Run Python monitor ─────────────────────────────────
echo ============================================================
echo   Starting KUKA monitor (Ctrl+C to stop monitor)
echo ============================================================
".venv\Scripts\python.exe" main_influxV2.py
pause
