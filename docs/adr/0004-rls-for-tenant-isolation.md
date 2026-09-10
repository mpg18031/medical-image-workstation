# ADR 0004 — Row-Level Security as the authorisation boundary

**Status:** Accepted · **Date:** 2026-01-12

## Context

Tenant and user isolation could be enforced purely in application code by adding
`WHERE org_id = ...` to every query, or in the database via PostgreSQL Row-Level Security.

## Decision

Enforce authorisation in **both** places. The API performs role checks for good error
messages; PostgreSQL RLS (with `FORCE ROW LEVEL SECURITY`) is the actual boundary.

## Consequences

**Positive**
- A forgotten `WHERE` clause becomes an empty result set, not a PHI disclosure.
- Ad-hoc queries, workers, and future services inherit the same isolation.
- The policy is auditable in one place and testable with pgTAP.

**Negative**
- Session context must be set on every transaction. `SET LOCAL` is mandatory — a plain
  `SET` would leak context to the next borrower of a pooled connection. Enforced by a
  repository base class and a pgTAP test that reuses a pooled connection across users.
- Small planner overhead; mitigated by leading indexes with `org_id` first.
- `FORCE` is required, otherwise the table owner silently bypasses its own policies.

## Alternatives rejected

- **Application-only filtering:** one missed clause is a reportable breach.
- **Separate schema or database per tenant:** stronger isolation, but migration and
  connection-pool overhead scale badly and cross-tenant research queries become impossible.
