const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");

/** Production online app (HTTPS). */
const APP_URL = process.env.INVENTORY_APP_URL || "https://app.rajagro.org";
const HEALTH_URL = `${APP_URL.replace(/\/$/, "")}/health/ready`;

let mainWindow = null;

function offlinePage() {
  return path.join(__dirname, "offline.html");
}

async function serverReachable(timeoutMs = 8000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(HEALTH_URL, {
      method: "GET",
      signal: controller.signal,
      cache: "no-store",
    });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

async function showAppOrOffline() {
  if (!mainWindow) return;
  const online = await serverReachable();
  if (online) {
    await mainWindow.loadURL(APP_URL);
  } else {
    await mainWindow.loadFile(offlinePage());
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    autoHideMenuBar: true,
    webPreferences: {
      // Needed so offline.html can call ipcRenderer.retry
      nodeIntegration: true,
      contextIsolation: false,
    },
  });

  showAppOrOffline();

  mainWindow.webContents.on("did-fail-load", (_event, errorCode, _desc, validatedURL) => {
    // Ignore aborted loads; show offline when the remote app fails.
    if (errorCode === -3) return;
    if (validatedURL && validatedURL.startsWith(APP_URL)) {
      mainWindow.loadFile(offlinePage());
    }
  });
}

ipcMain.handle("retry-online", async () => {
  const online = await serverReachable();
  if (online && mainWindow) {
    await mainWindow.loadURL(APP_URL);
    return true;
  }
  return false;
});

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
