---
name: lang-web
description: JavaScript and TypeScript — Node, npm, type checking, web UI menus, and Electron desktop app menus.
domain: web
triggers: javascript, js, typescript, ts, node, npm, npx, electron, react, vue, html, css, dom, .js, .ts, .tsx, tsconfig, package.json, web app, website, frontend, browser
---
# JavaScript / TypeScript skill

RUN / CHECK (always check before saying it works)
```
node --check file.js          # syntax only, no side effects
node file.js
npx tsc --noEmit              # type-check TypeScript
npm install && npm run dev
```

TYPESCRIPT basics — a minimal `tsconfig.json`
```json
{ "compilerOptions": { "target": "ES2022", "module": "ESNext", "moduleResolution": "bundler",
  "strict": true, "outDir": "dist" }, "include": ["src"] }
```
```ts
type Tool = { name: string; run: (arg: string) => Promise<string> };
function pick(tools: Tool[], name: string): Tool | undefined {
  return tools.find(t => t.name === name);     // Tool | undefined — check before use
}
```
`strict: true` is worth it; it catches the null/undefined bugs a model usually writes.

MENU BAR — Electron desktop app (the real native menu)
```js
// main.js  — the MAIN process, this is where the menu lives
const { app, BrowserWindow, Menu, dialog } = require("electron");
const fs = require("node:fs/promises");

function createWindow() {
  const win = new BrowserWindow({
    width: 1000, height: 700,
    webPreferences: { preload: __dirname + "/preload.js", contextIsolation: true, nodeIntegration: false },
  });
  win.loadFile("index.html");

  const menu = Menu.buildFromTemplate([
    {
      label: "File",
      submenu: [
        { label: "Open…", accelerator: "CmdOrCtrl+O", click: async () => {
            const { canceled, filePaths } = await dialog.showOpenDialog(win);
            if (!canceled) win.webContents.send("file:opened", await fs.readFile(filePaths[0], "utf8"));
          } },
        { type: "separator" },
        { role: "quit" },                   // roles give you the correct per-OS label
      ],
    },
    { label: "Edit", submenu: [{ role: "undo" }, { role: "redo" }, { type: "separator" }, { role: "copy" }, { role: "paste" }] },
    { label: "View", submenu: [{ role: "reload" }, { role: "toggleDevTools" }] },
  ]);
  Menu.setApplicationMenu(menu);            // app-wide menu (macOS puts it in the system bar)
}

app.whenReady().then(createWindow);
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
```
Keep `contextIsolation: true` and `nodeIntegration: false`, and expose only what you need from
`preload.js` via `contextBridge` — a renderer with full Node access is a security hole.

MENU — plain web page (no framework, no build step)
```html
<nav class="menubar">
  <button aria-haspopup="true" aria-expanded="false" data-menu="file">File</button>
  <ul id="file" role="menu" hidden><li role="menuitem" tabindex="-1">Open…</li></ul>
</nav>
<script>
document.querySelectorAll("[data-menu]").forEach(b => b.addEventListener("click", () => {
  const list = document.getElementById(b.dataset.menu);
  const open = !list.hidden;
  list.hidden = open;
  b.setAttribute("aria-expanded", String(!open));
}));
document.addEventListener("click", e => {            // click-away closes it
  if (!e.target.closest(".menubar")) document.querySelectorAll("[role=menu]").forEach(m => m.hidden = true);
});
document.addEventListener("keydown", e => { if (e.key === "Escape")
  document.querySelectorAll("[role=menu]").forEach(m => m.hidden = true); });
</script>
```
Give menus `role="menu"`, keyboard support and Escape-to-close, or they are unusable without a mouse.

TRAPS
- `await` only works inside an `async` function (or a top-level ES module).
- Electron: `dialog`, `Menu` and `fs` are MAIN-process only; the renderer talks to them over IPC.
- `require` vs `import` — pick one; `"type": "module"` in package.json makes `.js` files ESM.
- `==` coerces types; always use `===`.
- `document.getElementById` before the element exists returns null — run scripts after the DOM, or use `defer`.
