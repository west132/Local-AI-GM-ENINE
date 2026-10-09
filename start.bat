@echo off
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" || (echo Python 3.10 or newer is needed: https://www.python.org/downloads/ ^(tick "Add Python to PATH"^) & pause & exit /b 1)
if not exist .venv ( %PY% -m venv .venv || (echo Could not create the .venv folder. & pause & exit /b 1) )
call .venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt || (echo Installing the requirements failed. Check your internet connection and try again. & pause & exit /b 1)
python -m localgm.web --open
pause
