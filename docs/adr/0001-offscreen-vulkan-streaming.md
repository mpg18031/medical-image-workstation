# ADR 0001 — Off-screen Vulkan rendering with frame streaming

**Status:** Accepted · **Date:** 2026-01-05

## Context

The renderer must display GPU-rendered volumes inside an Electron window. Two options:
embed a Vulkan surface into a Chromium-owned `HWND`/`NSView`/`X11 Window`, or render
off-screen and stream encoded frames to a `<canvas>`.

## Decision

Render off-screen into a colour attachment, encode on the GPU, and stream frames over a
WebSocket to the renderer process.

## Consequences

**Positive**
- One code path serves both `local` and `server` deployment modes.
- Avoids Chromium/Vulkan surface interop, which is fragile and differs per platform and
  compositor (notably Wayland).
- Enables remote/thin-client use with no architectural change.
- The renderer process needs no GPU privileges, so the Electron sandbox stays intact.

**Negative**
- Adds encode + transfer + decode to the latency budget (~5 ms measured).
- Requires an encoder; NVENC where available, PNG fallback otherwise.
- Compression artefacts are unacceptable for diagnostic review — mitigated by the
  server-driven quality ladder, which sends a full-quality still frame once interaction
  stops.

## Alternatives rejected

- **Embedded surface:** lowest latency, but per-platform interop code and a broken sandbox.
- **WebGPU in the renderer:** would move rendering into Chromium, but forfeits CUDA/TensorRT
  interop and mature volume-rendering control.
