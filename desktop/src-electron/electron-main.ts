import { app, BrowserWindow, dialog, ipcMain, session, shell } from "electron";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { WebSocket } from "ws";

const currentDir = fileURLToPath(new URL(".", import.meta.url));

const API_ORIGIN = process.env.MIVW_API_ORIGIN ?? "http://127.0.0.1:8000";
const OIDC_ORIGIN = new URL(
  process.env.MIVW_OIDC_ISSUER ?? "http://127.0.0.1:8080/realms/mivw",
).origin;

if (process.platform === "linux") {
  app.commandLine.appendSwitch("disable-gpu");
}

if (process.env.MIVW_DEV_NO_SANDBOX === "1") {
  app.commandLine.appendSwitch("no-sandbox");
}

let mainWindow: BrowserWindow | undefined;
let renderSocket: WebSocket | undefined;

function contentSecurityPolicy(): string {
  return [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'", // Quasar injects scoped styles at runtime
    "img-src 'self' blob: data:",
    `connect-src 'self' ${API_ORIGIN} ${API_ORIGIN.replace(/^http/, "ws")} ${OIDC_ORIGIN}`,
    "font-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
    "frame-ancestors 'none'",
  ].join("; ");
}

function createWindow(): void {
  const preloadPath = path.resolve(
    currentDir,
    path.join(
      process.env.QUASAR_ELECTRON_PRELOAD_FOLDER!,
      "electron-preload" + process.env.QUASAR_ELECTRON_PRELOAD_EXTENSION!,
    ),
  );

  mainWindow = new BrowserWindow({
    width: 1600,
    height: 1000,
    minWidth: 1280,
    minHeight: 800,
    backgroundColor: "#101014", // dark by default: reading rooms are dim
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
      preload: preloadPath,
    },
  });

  mainWindow.once("ready-to-show", () => mainWindow?.show());
  void mainWindow.loadURL(process.env.APP_URL!);

  mainWindow.on("closed", () => {
    mainWindow = undefined;
  });
}

function hardenSession(): void {
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        "Content-Security-Policy": [contentSecurityPolicy()],
        "X-Content-Type-Options": ["nosniff"],
        "Referrer-Policy": ["no-referrer"],
      },
    });
  });

  // Deny every permission by default. Nothing in this app needs camera,
  // microphone, geolocation or notifications.
  session.defaultSession.setPermissionRequestHandler(
    (_wc, _permission, callback) => {
      callback(false);
    },
  );

  session.defaultSession.setPermissionCheckHandler(() => false);
}

// magic(4) version(H) codec(H) seq(I) w(H) h(H) renderTimeUs(I) payloadLen(I) reserved(8)
// Mirrors api/src/mivw_api/ws/render_ws.py's `_HEADER` struct.
const FRAME_HEADER_BYTES = 32;
const FRAME_MAGIC = "MIVW";

function closeRenderSocket(): void {
  if (!renderSocket) return;
  const socket = renderSocket;
  renderSocket = undefined;
  socket.removeAllListeners();
  if (
    socket.readyState === WebSocket.OPEN ||
    socket.readyState === WebSocket.CONNECTING
  ) {
    socket.close();
  }
}

function forwardRenderFrame(buffer: Buffer): void {
  if (
    buffer.length < FRAME_HEADER_BYTES ||
    buffer.toString("ascii", 0, 4) !== FRAME_MAGIC
  )
    return;

  const codec =
    ["raw-rgba8", "h264", "hevc", "png"][buffer.readUInt16LE(6)] ?? "raw-rgba8";
  const seq = buffer.readUInt32LE(8);
  const width = buffer.readUInt16LE(12);
  const height = buffer.readUInt16LE(14);
  const renderTimeUs = buffer.readUInt32LE(16);
  const payloadLen = buffer.readUInt32LE(20);
  const payload = buffer.subarray(
    FRAME_HEADER_BYTES,
    FRAME_HEADER_BYTES + payloadLen,
  );
  const frameData = new Uint8Array(payload.byteLength);
  frameData.set(payload);

  mainWindow?.webContents.send("render:frame", {
    data: Array.from(frameData),
    codec,
    seq,
    width,
    height,
    renderTimeUs,
  });
}

function connectRenderSocket(sessionToken: string): Promise<void> {
  closeRenderSocket();

  return new Promise((resolve, reject) => {
    const url = `${API_ORIGIN.replace(/^http/, "ws")}/ws/render?session=${encodeURIComponent(sessionToken)}`;
    const socket = new WebSocket(url);
    renderSocket = socket;

    socket.once("open", () => resolve());
    socket.once("error", (err) =>
      reject(err instanceof Error ? err : new Error(String(err))),
    );

    socket.on("message", (data, isBinary) => {
      if (isBinary && Buffer.isBuffer(data)) {
        forwardRenderFrame(data);
        return;
      }
      try {
        const message = JSON.parse(data.toString()) as {
          type?: string;
          title?: string;
        };
        if (message.type === "error") {
          mainWindow?.webContents.send(
            "render:error",
            message.title ?? "Render failed",
          );
        }
      } catch {
        // A malformed control message must not tear down a working stream.
      }
    });

    socket.on("close", () => {
      if (renderSocket === socket) renderSocket = undefined;
    });

    socket.on("error", (err) => {
      mainWindow?.webContents.send(
        "render:error",
        err instanceof Error ? err.message : "Render stream error",
      );
    });
  });
}

function registerIpcHandlers(): void {
  ipcMain.handle("app:info", () => ({
    version: app.getVersion(),
    mode: "local" as const,
    platform: process.platform,
    ...(process.env.MIVW_E2E === "1" ? { e2e: true } : {}),
    ...(process.env.MIVW_E2E_ROLE
      ? { e2eRole: process.env.MIVW_E2E_ROLE }
      : {}),
  }));

  ipcMain.handle("render:connect", async (_event, sessionToken: string) => {
    await connectRenderSocket(sessionToken);
  });

  ipcMain.handle("render:disconnect", () => {
    closeRenderSocket();
  });

  ipcMain.on("render:camera", (_event, state: string) => {
    const camera = JSON.parse(state) as object;
    renderSocket?.send(JSON.stringify({ type: "camera", ...camera }));
  });

  ipcMain.on("render:window-level", (_event, payload: string) => {
    const windowLevel = JSON.parse(payload) as object;
    renderSocket?.send(JSON.stringify({ type: "window", ...windowLevel }));
  });

  ipcMain.handle("ingest:pick-files", async () => {
    if (!mainWindow) return [];
    const result = await dialog.showOpenDialog(mainWindow, {
      title: "Select DICOM files to ingest",
      properties: ["openFile", "multiSelections"],
    });
    return result.canceled ? [] : result.filePaths;
  });
}

// Single instance: two processes competing for the same GPU session would
// fight over pinned volume memory.
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  void app.whenReady().then(() => {
    registerIpcHandlers();
    hardenSession();
    createWindow();
  });
}

app.on("web-contents-created", (_event, contents) => {
  // Block in-app navigation away from the packaged origin.
  contents.on("will-navigate", (event, url) => {
    if (new URL(url).origin !== new URL(process.env.APP_URL!).origin) {
      event.preventDefault();
    }
  });

  // Never open a renderer-controlled window; hand external links to the OS
  // browser instead, after validating the scheme.
  contents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://")) {
      void shell.openExternal(url);
    }
    return { action: "deny" };
  });

  contents.on("will-attach-webview", (event) => event.preventDefault());
});

app.on("window-all-closed", () => {
  closeRenderSocket();
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (mainWindow === undefined) createWindow();
});
