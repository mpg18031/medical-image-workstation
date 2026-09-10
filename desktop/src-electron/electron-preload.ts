/**
 * The renderer's entire privilege surface.
 *
 * Everything exposed here is explicitly enumerated. There is no generic
 * `invoke(channel, ...)` escape hatch, and no Node built-in is reachable from
 * the renderer. Adding to this file widens the attack surface, so each addition
 * needs a justification in review.
 */
import { contextBridge, ipcRenderer } from "electron";

export interface CameraState {
  eye: [number, number, number];
  target: [number, number, number];
  up: [number, number, number];
  fovDeg: number;
}

export interface FramePayload {
  data: number[];
  codec: "raw-rgba8" | "png" | "h264" | "hevc";
  seq: number;
  width: number;
  height: number;
  renderTimeUs: number;
}

export interface AppInfo {
  version: string;
  mode: "local" | "server";
  platform: NodeJS.Platform;
  e2e?: boolean;
  e2eRole?: Role;
}

type Role = "viewer" | "annotator" | "researcher" | "admin";

export interface MivwBridge {
  connectRenderStream(sessionToken: string): Promise<void>;
  disconnectRenderStream(): Promise<void>;
  sendCamera(state: CameraState): void;
  sendWindowLevel(center: number, width: number): void;
  onFrame(callback: (frame: FramePayload) => void): () => void;
  onStreamError(callback: (message: string) => void): () => void;
  /** Native file dialog. Returns paths only; the renderer never gets a handle. */
  pickFilesForIngest(): Promise<string[]>;
  getAppInfo(): Promise<AppInfo>;
}

const bridge: MivwBridge = {
  connectRenderStream: (sessionToken) =>
    ipcRenderer.invoke("render:connect", sessionToken),

  disconnectRenderStream: () => ipcRenderer.invoke("render:disconnect"),

  sendCamera: (state) =>
    ipcRenderer.send(
      "render:camera",
      JSON.stringify({
        eye: state.eye.map(Number),
        target: state.target.map(Number),
        up: state.up.map(Number),
        fovDeg: Number(state.fovDeg),
      }),
    ),

  sendWindowLevel: (center, width) =>
    ipcRenderer.send(
      "render:window-level",
      JSON.stringify({ center: Number(center), width: Number(width) }),
    ),

  onFrame: (callback) => {
    const listener = (_e: Electron.IpcRendererEvent, frame: FramePayload) =>
      callback(frame);
    ipcRenderer.on("render:frame", listener);
    return () => ipcRenderer.removeListener("render:frame", listener);
  },

  onStreamError: (callback) => {
    const listener = (_e: Electron.IpcRendererEvent, message: string) =>
      callback(message);
    ipcRenderer.on("render:error", listener);
    return () => ipcRenderer.removeListener("render:error", listener);
  },

  pickFilesForIngest: () => ipcRenderer.invoke("ingest:pick-files"),

  getAppInfo: () => ipcRenderer.invoke("app:info"),
};

contextBridge.exposeInMainWorld("mivw", bridge);

declare global {
  interface Window {
    mivw: MivwBridge;
  }
}
