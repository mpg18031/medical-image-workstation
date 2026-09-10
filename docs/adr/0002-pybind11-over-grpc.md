# ADR 0002 — pybind11 in-process bindings instead of a gRPC sidecar

**Status:** Accepted · **Date:** 2026-01-05

## Context

The FastAPI gateway must invoke the C++/CUDA core. The core could run as a separate
process behind gRPC, or be loaded in-process as a Python extension module.

## Decision

Build the core as a single `mivw_core` extension module via pybind11 and
scikit-build-core, loaded directly into the API process.

## Consequences

**Positive**
- No serialisation of volume data. A 512³ `int16` volume is 256 MB; a gRPC hop would cost
  hundreds of milliseconds and double the memory.
- Numpy views over C++ buffers are zero-copy.
- One process to deploy, profile, and trace.

**Negative**
- A segfault in C++ takes down the gateway. Mitigated by strict RAII, sanitizer builds in
  CI, and a supervisor that restarts workers.
- GIL contention risk. Mitigated by `py::gil_scoped_release` around every operation longer
  than ~100 µs; enforced by review checklist.
- The API process must be built against a matching ABI, so the build matrix is larger.

## Alternatives rejected

- **gRPC sidecar:** better fault isolation, unacceptable hot-path cost.
- **Shared memory + control channel:** recovers the copy cost but reintroduces a
  serialisation protocol and lifetime-management complexity for no clear gain.
