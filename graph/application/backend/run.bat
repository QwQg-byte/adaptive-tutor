@echo off
echo Killing existing processes on port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a 2>nul
)

echo Waiting...
ping -n 3 127.0.0.1 >nul

echo Starting server...
start "" python main.py

echo Done! Server should be running on http://localhost:8000
