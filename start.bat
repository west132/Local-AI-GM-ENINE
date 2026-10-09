@echo off
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
if not exist .venv ( %PY% -m venv .venv || (echo Python 3.10+ is needed: https://www.python.org/downloads/ & pause & exit /b 1) )
call .venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt
python -m localgm.web --open
pause
