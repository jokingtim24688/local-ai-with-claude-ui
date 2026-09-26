#!/usr/bin/env bash
# macOS / Linux build.   macOS -> dist/Ai Heaven.app      Linux -> dist/Ai Heaven
# (Windows: build.bat or build_nuitka.bat.)  Real compiled app instead:  python3 build_nuitka.py
set -e
cd "$(dirname "$0")"
[ -d buildenv ] || python3 -m venv buildenv        # clean env keeps the app small
source buildenv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm elysium.spec
if [ "$(uname)" = "Darwin" ]; then
  echo "Built: dist/Ai Heaven.app  (drag it to Applications)"
  echo "First launch of an unsigned app: right-click it -> Open."
else
  echo "Built: dist/Ai Heaven"
fi
