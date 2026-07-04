@echo off
cd /d "%~dp0\sourcecheck_backend"
if not exist ".venv" (
  python -m venv .venv
)
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn sourcecheck_api:app --host 127.0.0.1 --port 8000 --reload
