# Security Policy

## Regulatory status

MIVW is **Research Use Only**. It is not FDA-cleared, not CE-marked under the EU MDR, and
must not be used for primary diagnosis or treatment decisions. Reports that assume
clinical deployment will be answered on that basis.

## Reporting a vulnerability

**Do not open a public issue for security reports.**

Use GitHub's private vulnerability reporting (Security → Report a vulnerability) on this
repository. Include affected component, version or commit, reproduction steps, and impact.

We aim to acknowledge within 3 working days and to provide an assessment within 10.
Coordinated disclosure is preferred; we will agree a publication date with you.

## Never include patient data in a report

If a report requires imaging data, generate a synthetic case with
`scripts/make_fixtures.py`. Reports containing real PHI will be deleted without being
processed, and you will be asked to resubmit.

## Scope

In scope:

- Authentication and authorisation bypass, including cross-tenant access
- Row-Level Security bypass or session-context leakage across pooled connections
- PHI disclosure through API responses, logs, error messages, or telemetry
- De-identification gaps, including retained tags and burned-in pixel annotation
- Electron sandbox escape, CSP bypass, or privilege escalation through the preload bridge
- SQL injection, path traversal, SSRF, deserialisation flaws
- Model artefact substitution or supply-chain tampering
- Cryptographic weaknesses in the PHI encryption or HMAC lookup design

Out of scope:

- Findings that require an already-compromised host or a malicious administrator
- Denial of service through raw traffic volume
- Missing hardening headers on `local`-mode loopback endpoints
- Vulnerabilities in the development-only Docker Compose stack (Keycloak, MinIO), which
  ship with placeholder credentials by design and are never deployed

## Security-relevant design

The controls and threat model are documented in
[docs/06-security-compliance.md](docs/06-security-compliance.md). Three areas carry a
two-approval review requirement because a mistake there becomes a PHI incident:

- `db/migrations/` — RLS policies and grants
- `api/src/mivw_api/security/` — authentication and authorisation
- `core/src/dicom/deid*` — de-identification

## Supported versions

| Version | Supported |
| --- | --- |
| `main` | Yes |
| Latest tagged release | Yes |
| Older releases | No |
