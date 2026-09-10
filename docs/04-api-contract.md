# 04 — API Contract

Base path `/api/v1`. All responses are JSON except WebSocket binary frames.
The OpenAPI document is generated from the Pydantic v2 schemas and is the **normative**
source; this file describes intent and invariants.

## 1. Conventions

| Concern | Rule |
| --- | --- |
| Auth | `Authorization: Bearer <JWT>` from the OIDC provider. Verified against cached JWKS. |
| Errors | RFC 9457 `application/problem+json` |
| Idempotency | `Idempotency-Key` header required on all `POST` that create work |
| Pagination | Keyset: `?limit=&after=<opaque cursor>`. Offset pagination is not offered. |
| Correlation | `X-Request-Id` echoed; used as the OpenTelemetry trace ID |
| Versioning | Path-versioned. Breaking changes require `/api/v2`. |

### Error shape

```json
{
  "type": "https://mivw.local/problems/volume-spec-mismatch",
  "title": "Volume does not satisfy model input specification",
  "status": 422,
  "detail": "Model expects spacing 1.0x1.0x1.0 mm; volume is 0.7x0.7x3.0 mm",
  "instance": "/api/v1/inference-runs",
  "requestId": "01J8Z...",
  "errors": [{ "field": "volumeAssetId", "code": "spec_mismatch" }]
}
```

`detail` never contains PHI. Validation messages reference field names and constraint
codes, not values.

## 2. REST surface

### Studies and series

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| `GET` | `/studies` | viewer | Keyset paginated worklist; filters `modality`, `from`, `to`, `patientRef` |
| `GET` | `/studies/{studyId}` | viewer | 404 (not 403) when RLS filters it out |
| `GET` | `/studies/{studyId}/series` | viewer | |
| `GET` | `/series/{seriesId}` | viewer | Includes geometry block |
| `GET` | `/series/{seriesId}/volume` | viewer | Returns a short-lived presigned object URL |
| `DELETE` | `/studies/{studyId}` | admin | Soft delete; schedules an erasure job |

`patientRef` is matched against `mrn_hmac`; the raw MRN is HMAC'd by the gateway and never
logged.

### Ingest

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| `POST` | `/ingest/sessions` | researcher | Opens an upload session, returns presigned targets |
| `POST` | `/ingest/sessions/{id}/complete` | researcher | Enqueues an `ingest` job |
| `GET` | `/ingest/sessions/{id}` | researcher | Session state and per-file results |

Uploads bypass the API process and go directly to the object store via presigned PUT, so a
multi-gigabyte study never occupies a gateway worker.

### Models

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/models` | viewer |
| `GET` | `/models/{modelId}` | viewer |
| `POST` | `/models` | admin |
| `PATCH` | `/models/{modelId}` | admin |
| `POST` | `/models/{modelId}/validate` | admin |

`POST /models` registers an already-uploaded ONNX artefact. The gateway recomputes the
SHA-256 and rejects a mismatch. `validate` performs a dry-run load and a synthetic-input
inference so a broken model is discovered at registration, not at clinical use.

```jsonc
// POST /models
{
  "name": "liver-seg",
  "version": "1.4.0",
  "artifactKey": "models/liver-seg-1.4.0.onnx",
  "artifactSha256": "9f86d0818...",
  "outputKind": "segmentation",
  "inputSpec": {
    "shape": [1, 1, 128, 128, 128],
    "spacingMm": [1.0, 1.0, 1.0],
    "orientation": "RAS",
    "normalisation": { "kind": "zscore", "clipHu": [-200, 300] }
  },
  "labelMap": { "1": { "name": "liver", "color": "#d94f3d" } }
}
```

### Inference

| Method | Path | Role |
| --- | --- | --- |
| `POST` | `/inference-runs` | researcher |
| `GET` | `/inference-runs/{runId}` | viewer |
| `GET` | `/inference-runs/{runId}/segmentation` | viewer |

`POST` returns `202 Accepted` with a job handle. Progress arrives on `/ws/jobs`.

### Annotations

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/series/{seriesId}/annotations` | viewer |
| `POST` | `/series/{seriesId}/annotations` | annotator |
| `PATCH` | `/annotations/{id}` | annotator (author or admin) |
| `DELETE` | `/annotations/{id}` | annotator (author or admin) |

Geometry is submitted in **patient coordinates (mm)** with an explicit
`frameOfReferenceUid`. The gateway rejects pixel-index geometry.

### Render sessions

| Method | Path | Role |
| --- | --- | --- |
| `POST` | `/render/sessions` | viewer |
| `DELETE` | `/render/sessions/{id}` | viewer |

Creating a session pins the volume into GPU memory and returns a session token used to
open the render WebSocket. Sessions expire after an idle timeout so GPU memory cannot be
squatted.

### Operational

| Method | Path | Auth |
| --- | --- | --- |
| `GET` | `/healthz` | none — liveness only, no detail |
| `GET` | `/readyz` | none — dependency readiness |
| `GET` | `/metrics` | internal network only |

## 3. WebSocket channels

### `/ws/render?session=<token>`

Client → server (JSON text frames):

```jsonc
{ "type": "camera",   "seq": 412, "eye": [0,0,-500], "target": [0,0,0], "up": [0,1,0], "fovDeg": 45 }
{ "type": "transfer", "seq": 413, "presetId": "ct-bone" }
{ "type": "window",   "seq": 414, "center": 40, "width": 400 }
{ "type": "layers",   "seq": 415, "segmentationVisible": true, "opacity": 0.45 }
{ "type": "quality",  "seq": 416, "mode": "interactive" }   // interactive | still
```

Server → client:

- **Binary frame:** 32-byte little-endian header + payload.
  `magic(4) | version(u16) | codec(u16) | seq(u32) | width(u16) | height(u16) | renderTimeUs(u32) | payloadLen(u32) | reserved(8)`
- **Text frame:** `{"type":"error", ...}` using the same problem-detail body.

**Backpressure — latest wins.** If a newer `camera` message arrives while a frame is in
flight, the in-flight frame is completed but any *queued* request is discarded. The client
must tolerate skipped `seq` values. This trades throughput for responsiveness, which is
the correct choice for direct manipulation.

**Quality ladder.** `interactive` renders at half resolution with a coarser step size;
after 150 ms of input quiescence the server automatically emits a `still` frame at full
quality. The client does not request this — it is server-driven so it adapts to actual GPU
load.

### `/ws/jobs`

Server-push job lifecycle:

```jsonc
{ "type": "job.progress", "jobId": "...", "kind": "inference", "progress": 0.62, "stage": "sliding-window" }
{ "type": "job.completed", "jobId": "...", "result": { "inferenceRunId": "..." } }
{ "type": "job.failed",    "jobId": "...", "problem": { "type": "...", "title": "..." } }
```

## 4. Security controls on the API surface

| Control | Implementation |
| --- | --- |
| Transport | TLS 1.3 required in `server` mode; loopback-only in `local` mode |
| Token | RS256/ES256 JWT; `aud`, `iss`, `exp`, `nbf` all verified; 5 s clock skew |
| Authorisation | Dependency-injected role check **plus** database RLS |
| Rate limiting | Per-subject token bucket; separate stricter bucket for `/ingest` and `/models` |
| Body limits | 1 MB JSON; uploads never traverse the gateway |
| CORS | Disabled by default; `server` mode allows only the packaged client origin |
| Headers | HSTS, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, restrictive CSP |
| WS origin | Origin checked on upgrade — a WebSocket handshake is not covered by CORS |
| Presigned URLs | 5-minute TTL, single method, response headers pinned |
| Logging | Structured; a redaction filter drops known PHI field names before emit |

## 5. Client generation

`make openapi` exports `openapi.json`; `make api-client` regenerates the typed TypeScript
client into `desktop/src/services/generated/`. The generated directory is committed and
CI fails if regeneration produces a diff — this makes an accidental breaking API change
visible in review.
