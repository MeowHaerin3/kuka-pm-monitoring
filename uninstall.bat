@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
chcp 65001 >nul

echo ============================================================
echo   KUKA EIP Monitoring - Uninstaller
echo ============================================================
echo.
echo This will remove ALL installed/extracted files in this folder:
echo.
echo   [1] Running processes  : python.exe (monitor)
echo   [2] Virtual env        : .venv\
echo   [3] Extracted runtimes : installer\uv\
echo   [4] Python cache       : __pycache__\
echo.
echo Files KEPT (so you can re-run run_scripts.bat later):
echo   - installer\*.zip / *.exe (original archives)
echo   - installer\wheels\, requirements.txt
echo   - config.json, main_influxV2.py, run_scripts.bat, stop_scripts.bat
echo.

set /p CONFIRM="Type YES to proceed: "
if /I not "!CONFIRM!"=="YES" (
    echo Aborted.
    pause
    exit /b 0
)

echo.
echo --- [1/4] Stopping processes ---
REM Kill python monitor
for /f "tokens=2 delims=," %%P in ('tasklist /FI "IMAGENAME eq python.exe" /FO CSV /NH 2^>nul') do (
    taskkill /F /PID %%~P >nul 2>&1
)
timeout /t 2 /nobreak >nul

echo.
echo --- [2/4] Removing .venv ---
if exist ".venv" (
    rmdir /S /Q ".venv" 2>nul
    if exist ".venv" (
        echo [WARN] Could not fully remove .venv (file in use?). Try closing editors/terminals and re-run.
    ) else (
        echo [OK]   .venv removed.
    )
) else (
    echo [SKIP] .venv not present.
)

echo.
echo --- [3/4] Removing extracted runtimes in installer\ ---
if exist "installer\uv" (
    rmdir /S /Q "installer\uv" 2>nul && echo [OK]   installer\uv removed.
) else ( echo [SKIP] installer\uv not present. )

echo.
echo --- [4/4] Removing Python cache ---
if exist "__pycache__" (
    rmdir /S /Q "__pycache__" 2>nul && echo [OK]   __pycache__ removed.
) else ( echo [SKIP] __pycache__ not present. )

echo.
echo ============================================================
echo   Local uninstall complete.
echo ============================================================
echo.
echo NOTE: Python 3.12 (if installed by run_scripts.bat to
echo       %%LOCALAPPDATA%%\Programs\Python\Python312\) is NOT removed
echo       because other apps may depend on it.
echo       To remove manually: Windows Settings -^> Apps -^> "Python 3.12.10"
echo.
pause
endlocal
