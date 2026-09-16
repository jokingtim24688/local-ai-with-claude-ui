@echo off
REM Build the standalone Elysium.exe (Windows)
pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm elysium.spec
echo.
echo Built. Your app is dist\Elysium.exe
pause
