---
name: lang-python
description: Python apps — project layout, running, and desktop GUIs with real menu bars (Tkinter, PySide6).
domain: python
triggers: python, py, pip, tkinter, pyside, pyqt, flask, fastapi, venv, requirements.txt, argparse, pytest, .py, python script
---
# Python skill

RUN / CHECK (always verify your own work)
```
python -m py_compile file.py      # syntax only, no side effects
python file.py                    # run it
python -m pytest -q               # tests
pip install -r requirements.txt
```
Write a file, then run `python -m py_compile` on it before saying it works.

LAYOUT for an app
```
app/__init__.py  main.py  ui.py  requirements.txt  README.md
```
Entry point always ends with:
```python
if __name__ == "__main__":
    main()
```

DESKTOP MENU BAR — Tkinter (in the standard library, nothing to install)
```python
import tkinter as tk
from tkinter import filedialog, messagebox

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("My App")
        self.geometry("900x600")
        self._menu()
        self.text = tk.Text(self); self.text.pack(fill="both", expand=True)

    def _menu(self):
        bar = tk.Menu(self)
        file = tk.Menu(bar, tearoff=0)          # tearoff=0 or you get a dashed line
        file.add_command(label="Open…", command=self.open, accelerator="Ctrl+O")
        file.add_separator()
        file.add_command(label="Quit", command=self.destroy)
        bar.add_cascade(label="File", menu=file)
        help_ = tk.Menu(bar, tearoff=0)
        help_.add_command(label="About", command=lambda: messagebox.showinfo("About", "My App 1.0"))
        bar.add_cascade(label="Help", menu=help_)
        self.config(menu=bar)                    # REQUIRED, the bar does not show without it
        self.bind_all("<Control-o>", lambda e: self.open())

    def open(self):
        p = filedialog.askopenfilename()
        if p:
            self.text.insert("1.0", open(p, encoding="utf-8").read())

App().mainloop()
```

DESKTOP MENU BAR — PySide6 (`pip install PySide6`), for a richer app
```python
from PySide6.QtWidgets import QApplication, QMainWindow, QTextEdit, QFileDialog
from PySide6.QtGui import QAction, QKeySequence

class Win(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setCentralWidget(QTextEdit())
        f = self.menuBar().addMenu("&File")       # & marks the Alt shortcut letter
        act = QAction("&Open…", self, shortcut=QKeySequence.Open, triggered=self.open)
        f.addAction(act); f.addSeparator()
        f.addAction(QAction("&Quit", self, shortcut=QKeySequence.Quit, triggered=self.close))

    def open(self):
        p, _ = QFileDialog.getOpenFileName(self)
        if p:
            self.centralWidget().setPlainText(open(p, encoding="utf-8").read())

app = QApplication([]); w = Win(); w.show(); app.exec()
```

TRAPS
- Keep a reference to a Tk image (`self.img = PhotoImage(...)`) or it is garbage-collected and shows blank.
- `tearoff=0` on every Tk menu.
- PySide6: `QAction` is in `QtGui`, not `QtWidgets` (that moved in Qt6).
- Never a mutable default: `def f(items=[])` is a bug; use `None`.
- Write UTF-8 explicitly: `open(p, encoding="utf-8")` — Windows defaults to cp1252.
