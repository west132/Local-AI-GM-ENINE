#!/bin/sh
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv || exit 1
. .venv/bin/activate
python -m pip install -q -r requirements.txt
python -m localgm.web --open
