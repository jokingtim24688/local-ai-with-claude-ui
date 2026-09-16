#!/usr/bin/env bash
set -e
pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm elysium.spec
echo "Built. Your app is in dist/"
