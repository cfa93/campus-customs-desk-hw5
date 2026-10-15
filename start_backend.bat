@echo off
rem Starts the Campus Customs Desk API on http://127.0.0.1:8000 (docs at /docs).
rem Works from any folder; press Ctrl+C to stop.
cd /d "%~dp0backend"
python -m uvicorn main:app --reload --port 8000
