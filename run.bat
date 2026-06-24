@echo off
cd /d "%~dp0"
set PYTHONPATH=%CD%
python -m uvicorn BACKEND.app:app --host 127.0.0.1 --port 8000 --reload
