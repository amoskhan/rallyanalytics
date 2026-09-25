@echo off
rem Starts the RallyBook analysis server and opens the video page.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run setup first:  powershell -ExecutionPolicy Bypass -File setup.ps1
  pause
  exit /b 1
)
start "" http://localhost:8765/video.html
.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8765
pause
