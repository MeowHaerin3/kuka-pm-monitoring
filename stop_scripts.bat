@echo off
echo [STOP] Stopping KUKA monitor...
for /f "tokens=2 delims=," %%P in ('tasklist /FI "IMAGENAME eq python.exe" /FO CSV /NH 2^>nul') do (
    taskkill /F /PID %%~P >nul 2>&1
)
echo [OK]   Monitor stopped.
echo.
echo Done.
timeout /t 2 /nobreak >nul
