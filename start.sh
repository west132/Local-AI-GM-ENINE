#!/bin/sh
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Python 3.10 or newer is needed: https://www.python.org/downloads/"; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || { echo "Python 3.10 or newer is needed (you have $(python3 -V))."; exit 1; }
[ -d .venv ] || python3 -m venv .venv || { echo "Could not make the .venv folder (on Debian/Ubuntu: sudo apt install python3-venv)."; exit 1; }
. .venv/bin/activate
python -m pip install -q -r requirements.txt || { echo "Installing the requirements failed. Check your internet connection and try again."; exit 1; }
python -m localgm.web --open
