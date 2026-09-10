# 06 — Security & Compliance

> **Regulatory status.** MIVW is **Research Use Only**. It is not FDA-cleared,
> not CE-marked under the EU MDR, and must not be used for primary diagnosis or
> treatment decisions. The disclaimer is displayed at launch and is not dismissible
> permanently. If this project ever targets clinical use, it becomes Software as a
> Medical Device and requires IEC 62304 lifecycle processes, ISO 14971 risk management,
> and a regulatory submission. That is out of scope here, and the architecture should not
> pretend otherwise.

## 1. Threat model (STRIDE)

| Threat | Vector | Mitigation |
| --- | --- | --- |
| **Spoofing** | Forged JWT | Asymmetric signature, JWKS pinning, `aud`/`iss`/`exp` verified, `alg: none` rejected |
| **Spoofing** | Malicious render-server impersonation | mTLS with certificate pinning in `server` mode |
| **Tampering** | Swapped ONNX model artefact | SHA-256 digest verified before every load; registry digest is immutable |
| **Tampering** | Modified volume in object store | Content hash verified on read |
| **Repudiation** | Denying a PHI access | Append-only partitioned audit log; `UPDATE`/`DELETE` revoked and trigger-blocked |
| **Information disclosure** | Database dump | Column-level `pgcrypto` on direct identifiers, key held outside the DB |
| **Information disclosure** | Cross-tenant read via app bug | RLS with `FORCE`; app role lacks `BYPASSRLS` |
| **Information disclosure** | PHI in logs or error bodies | Redaction filter; problem details never echo values |
| **Information disclosure** | Existence leak via status codes | Unauthorised resources return 404, not 403 |
| **Denial of service** | Malicious DICOM (decompression bomb) | Declared-size limits, pixel-count caps, parse in a resource-limited worker |
| **Denial of service** | GPU memory squatting | Render sessions expire on idle; per-user session cap |
| **Denial of service** | Unbounded upload | Direct-to-object-store presigned PUT with size limit; gateway never buffers |
| **Elevation of privilege** | Renderer → OS via Electron | `contextIsolation`, `sandbox`, `nodeIntegration: false`, enumerated preload surface, no `remote` |
| **Elevation of privilege** | SQL injection | Parameterised statements only; no string-built SQL; enforced by lint rule and test |
| **Elevation of privilege** | Path traversal in ingest | Object keys are derived from content hashes, never from user input |

## 2. DICOM de-identification

Applied on ingest, before any persistence outside the sandbox, per **DICOM PS3.15
Annex E Basic Confidentiality Profile**.

| Action | Tags |
| --- | --- |
| Remove | Patient name/ID/address/phone, referring physician, institution, operator, device serial, all private tags, all curve/overlay data |
| Replace with pseudonym | Patient ID, all UIDs (Study/Series/SOP/Frame of Reference) — consistently, so relationships survive |
| Coarsen | Birth date → birth year; study date → configurable offset applied consistently per patient |
| Retain | Modality, geometry, acquisition parameters — required for correct rendering |

**Burned-in pixel annotation** is the failure mode people forget: header scrubbing does
nothing about text rendered into the image. Ingest checks `BurnedInAnnotation` and, when
it is `YES` or absent for at-risk modalities (US, XA, CR, SC), routes the series to
quarantine for review rather than accepting it.

The pseudonym mapping lives in `deid_map`, encrypted, readable only by `mivw_reidentify` —
a role that the application never assumes. Re-identification requires a deliberate,
separately audited administrative action.

## 3. Cryptography

| Data state | Control |
| --- | --- |
| In transit (server mode) | TLS 1.3, modern ciphers only; mTLS between client and render node |
| In transit (local mode) | Loopback binding; no network exposure |
| At rest — database | Full-disk/volume encryption **plus** column-level `pgp_sym_encrypt` on direct identifiers |
| At rest — object store | SSE-KMS, per-tenant key |
| At rest — client cache | Frames are held in memory only; no pixel data written to client disk |
| Keys | External KMS or OS keychain in local mode; never in source, env files, or the database |
| Searchable identifiers | Keyed HMAC-SHA256 column, not deterministic encryption (avoids frequency analysis) |

Key rotation is supported by storing a key ID alongside each ciphertext, so re-encryption
can proceed incrementally rather than requiring a maintenance window.

## 4. Authentication and authorisation

Authentication is delegated to an external OIDC provider — **no password material is ever
stored**. Short-lived access tokens (≤ 15 min) with refresh handled in the Electron main
process; tokens are never exposed to the renderer.

Authorisation is enforced **twice**, deliberately:

1. At the API, via a role-checking dependency — produces good error messages.
2. At the database, via RLS — survives a bug in layer 1.

| Role | Capabilities |
| --- | --- |
| `viewer` | Read studies/series/annotations, render, run no jobs |
| `annotator` | `viewer` + create/edit own annotations |
| `researcher` | `annotator` + ingest, run inference, export de-identified data |
| `admin` | `researcher` + manage users and model registry |
| `mivw_reidentify` | Database-only role for authorised re-identification; not assignable in-app |

Least privilege applies to database roles too: `mivw_app` has `SELECT/INSERT/UPDATE` on
data tables, `INSERT`-only on `audit_log`, and no DDL rights whatsoever.

## 5. Electron hardening

```ts
new BrowserWindow({
  webPreferences: {
    contextIsolation: true,
    nodeIntegration: false,
    sandbox: true,
    webSecurity: true,
    allowRunningInsecureContent: false,
    preload: path.join(__dirname, 'preload.js'),
  },
});
```

Additionally:
- CSP: `default-src 'self'; script-src 'self'; connect-src 'self' <api-origin>; img-src 'self' blob: data:; object-src 'none'; frame-ancestors 'none'`
- `app.on('web-contents-created')` blocks `will-navigate` to external origins and denies
  all `setWindowOpenHandler` requests.
- `session.setPermissionRequestHandler` denies everything not explicitly needed.
- Auto-update over HTTPS with signature verification; releases are code-signed and
  notarised on macOS.
- ASAR integrity checking enabled.

## 6. Supply chain

| Control | Tool |
| --- | --- |
| Dependency pinning | `uv.lock`, `package-lock.json`, CMake `FetchContent` with git SHAs |
| Vulnerability scanning | `pip-audit`, `npm audit`, `osv-scanner`, Trivy |
| SBOM | CycloneDX generated per release artefact |
| Artefact signing | Sigstore/cosign for containers; platform signing for installers |
| Model artefacts | SHA-256 pinned in the registry and verified at load |
| Secrets | `gitleaks` at pre-commit and in CI |

## 7. Logging and audit

**Audited events:** authentication (success and failure), every PHI read, every export,
every annotation mutation, every model registration and inference run, every
re-identification, every permission denial, and all administrative actions.

**Never logged:** patient names, MRNs, tokens, keys, decrypted values, request bodies of
PHI-bearing endpoints. A structured-logging redaction processor drops known-sensitive keys
and a unit test asserts the processor is installed.

Logs are shipped to an append-only sink with a retention of at least six years.

## 8. Compliance mapping

| Requirement | Where satisfied |
| --- | --- |
| HIPAA §164.312(a)(1) Access control | OIDC + RBAC + RLS |
| HIPAA §164.312(a)(2)(iv) Encryption | pgcrypto, SSE-KMS, TLS 1.3 |
| HIPAA §164.312(b) Audit controls | Append-only partitioned `audit_log` |
| HIPAA §164.312(c)(1) Integrity | Content hashes, digest-pinned models |
| HIPAA §164.312(e)(1) Transmission security | TLS 1.3 / mTLS |
| HIPAA §164.514(b) De-identification | PS3.15 Basic Profile + date coarsening |
| GDPR Art. 5(1)(c) Minimisation | Only geometry-relevant tags retained |
| GDPR Art. 17 Erasure | Delete `deid_map` → data becomes anonymous |
| GDPR Art. 25 Data protection by design | Pseudonymisation before persistence |
| GDPR Art. 32 Security of processing | Sections 3–6 above |

## 9. Incident response

Detection via alerts on: authentication failure spikes, unusual PHI read volume per user,
re-identification role usage, audit-log write failures (which must fail the transaction,
not be swallowed), and integrity-check failures.

A suspected breach triggers: session revocation, forensic export of the relevant audit
partitions, and the HIPAA Breach Notification Rule assessment — 60-day notification clock
where applicable.
