@echo off
cd /d "%~dp0"
set "PYTHONPATH=%CD%"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m uvicorn BACKEND.app:app --host 127.0.0.1 --port 8000
) else (
  python -m uvicorn BACKEND.app:app --host 127.0.0.1 --port 8000
)
