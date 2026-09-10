# ADR 0003 — Pixel data in object storage, metadata in PostgreSQL

**Status:** Accepted · **Date:** 2026-01-12

## Context

A single CT study is 100 MB–2 GB. Storing pixel data as `bytea` or large objects in
PostgreSQL is possible but affects the whole database's operational profile.

## Decision

Store volumes and DICOM instances in an S3-compatible object store (MinIO locally),
keyed by content SHA-256. PostgreSQL stores only metadata and the object key.

## Consequences

**Positive**
- Database stays small: backups are fast, `VACUUM` cost is bounded, replication is cheap.
- Content-hash keys give deduplication and integrity verification for free.
- Object lifecycle rules implement retention without application code.
- Presigned URLs let large uploads and downloads bypass the API process entirely.

**Negative**
- Two systems must stay consistent. Orphaned objects are handled by a reconciliation job;
  the database is the source of truth and unreferenced objects are reaped after a grace
  period.
- Transactional guarantees do not span both stores. Mitigated by writing the object first
  and the metadata row second, so a failure leaves an unreferenced object rather than a
  dangling reference.
- Adds a dependency to the local development stack.

## Alternatives rejected

- **`bytea` in PostgreSQL:** simple and transactional, but backup and vacuum cost make it
  untenable at study scale.
- **Filesystem paths:** works for `local` mode only; no server-mode story, and path
  handling from user input is a traversal risk.
