@echo off
REM Compile Night Crew to a real native .exe (Nuitka), output straight to Desktop
setlocal
cd /d "%~dp0"
where python >nul 2>&1 || (echo Install Python 3.10+ first & pause & exit /b 1)
python -m pip install --quiet nuitka
python -m nuitka --standalone --onefile --assume-yes-for-downloads ^
  --windows-console-mode=disable ^
  --windows-icon-from-ico=assets\icon.ico ^
  --company-name="Night Crew" --product-name="Night Crew" ^
  --file-version=0.1.0 --product-version=0.1.0 ^
  --include-data-dir=static=static ^
  --include-data-dir=assets=assets ^
  --include-data-dir=skills=skills ^
  --include-data-files=branding.json=branding.json ^
  --output-dir="%OneDrive%\Desktop" ^
  --output-filename="Night Crew.exe" ^
  desktop.py
echo.
if errorlevel 1 (
  echo BUILD FAILED — see the error above.
) else (
  echo Built. Your compiled app is on your Desktop: "Night Crew.exe"
)
pause
