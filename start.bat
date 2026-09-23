@echo off
echo ============================================
echo   AgriSaathi Edge AI — Starting...
echo ============================================

REM Kill anything already on port 8080
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8080 ^| findstr LISTENING 2^>nul') do taskkill /F /PID %%a >nul 2>&1

REM Start server in a new window
start "AgriSaathi Server" "%~dp0venv\Scripts\python.exe" "%~dp0main.py"

REM Wait for server to boot
timeout /t 3 /nobreak >nul

REM Start serial bridge in a new window
start "AgriSaathi Bridge" "%~dp0venv\Scripts\python.exe" "%~dp0serial_bridge.py"

REM Get current IP for phone access
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr "IPv4"') do (
    set IP=%%a
    goto :found
)
:found
set IP=%IP: =%

echo.
echo  Laptop URL : http://localhost:8080
echo  Phone URL  : http://%IP%:8080
echo.
echo  Make sure your phone is on the same WiFi.
echo  Close the two terminal windows to stop.
echo.
pause
