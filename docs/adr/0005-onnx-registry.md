# ADR 0005 — Pluggable ONNX model registry with digest pinning

**Status:** Accepted · **Date:** 2026-01-19

## Context

The workstation should not be tied to one clinical task. Users need to bring their own
models, but arbitrary model loading is a supply-chain and correctness risk.

## Decision

Models are registry entries describing an ONNX artefact, its SHA-256 digest, a declared
input specification, and an output kind. The core verifies the digest before every load
and validates the input volume against the declared specification, refusing to run on a
mismatch. TensorRT engines are cached per `(digest, gpu_arch, trt_version)`.

## Consequences

**Positive**
- Task-agnostic: segmentation, classification, heatmaps, and landmarks are all supported
  without core changes.
- Digest pinning prevents artefact substitution.
- Explicit rejection on spec mismatch prevents silently wrong results from mis-resampled
  input — the most dangerous failure mode in a medical imaging tool, because it produces a
  plausible-looking answer.
- Provenance records make every result reproducible and auditable.

**Negative**
- Users must author an accurate `inputSpec`. Mitigated by `POST /models/{id}/validate`,
  which dry-runs the model at registration time.
- No automatic adaptation to a model's preferred spacing. This is intentional: silent
  resampling would trade a loud failure for a quiet one.
- Engine cache can grow; bounded by an LRU eviction policy.

## Alternatives rejected

- **Hard-coded bundled model:** simpler, but limits the product to one task and one
  anatomy.
- **Accept any ONNX and auto-adapt input:** convenient, clinically unsafe.
