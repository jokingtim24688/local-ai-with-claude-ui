// Electron main process.
// Spawns the Python backend (Ollama bridge + tool engine), then opens the
// app window. No terminal panel is ever shown to the user — the backend runs
// hidden and the window is a real desktop app, not a browser.

const { app, BrowserWindow, ipcMain } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");

const ROOT = path.join(__dirname, "..");
const BACKEND_URL = "http://127.0.0.1:5173";
let backend = null;
let win = null;

function startBackend() {
  const py = process.platform === "win32" ? "python" : "python3";
  backend = spawn(py, ["app.py", "--workdir", "./workspace", "--skills", "./skills"], {
    cwd: ROOT,
    stdio: "ignore",
    windowsHide: true,
  });
  backend.on("error", (e) => console.error("backend spawn failed:", e.message));
}

function waitForBackend(cb, tries = 60) {
  http.get(BACKEND_URL + "/api/config", (res) => { res.resume(); cb(); })
    .on("error", () => {
      if (tries <= 0) return cb(); // load anyway; UI shows offline state
      setTimeout(() => waitForBackend(cb, tries - 1), 500);
    });
}

function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: "#0e1013",
    titleBarStyle: "hiddenInset",
    title: "Local AI",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
    },
  });
  win.loadURL(BACKEND_URL);
}

ipcMain.handle("app:info", () => ({ backend: BACKEND_URL, root: ROOT }));

app.whenReady().then(() => {
  startBackend();
  waitForBackend(createWindow);
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (backend) backend.kill();
  if (process.platform !== "darwin") app.quit();
});
app.on("before-quit", () => { if (backend) backend.kill(); });
