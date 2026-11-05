#!/bin/bash
cd "$(dirname "$0")"
echo "Starting ShelfWise..."
python3 -m pip install -q --disable-pip-version-check -r requirements.txt
python3 run.py
