---
name: desktop-automation
description: Automate the OS: launch/kill processes, open files/URLs, hotkeys, screenshots.
---

# desktop-automation

Cross-platform launch/kill and I/O.

- Open app/file/URL: Windows `os.startfile(x)` · macOS `open x` · Linux `xdg-open x`
- Run/background a process: `subprocess.Popen([...])`; capture: `subprocess.run([...], capture_output=True, text=True)`
- Is it running / kill it: `psutil` — `psutil.process_iter(["name"])`, `p.terminate()`
- Install apps (Windows): `winget install <pkg>`
- GUI automation (type, click, hotkey): `pyautogui` — `pyautogui.hotkey("ctrl","c")`, `pyautogui.screenshot("s.png")`
- Global hotkeys: `keyboard` lib — `keyboard.add_hotkey("ctrl+alt+m", fn)`

Build a launcher dashboard: one button per action → subprocess/URI/REST. Keep
persistent auth for API-controlled apps (Spotify, Cast) so buttons act instantly.
