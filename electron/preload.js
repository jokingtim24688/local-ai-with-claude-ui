const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("desktop", {
  info: () => ipcRenderer.invoke("app:info"),
  isElectron: true,
});
