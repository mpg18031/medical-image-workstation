## What and why

<!-- What changes, and what problem it solves. Link the issue. -->

Closes #

## How

<!-- Design notes a reviewer needs. Call out anything non-obvious. -->

## Testing

- [ ] Tests added at the lowest layer that reproduces the behaviour
- [ ] `make lint` passes
- [ ] `make test` passes locally

| Layer | Covered |
| --- | --- |
| pgTAP | <!-- yes / n/a --> |
| GoogleTest | |
| pytest | |
| Vitest | |
| Storybook | |
| Playwright | |

## Patient data

- [ ] No real patient data in code, fixtures, tests, logs, or screenshots
- [ ] Any new DICOM fixtures were produced by `scripts/make_fixtures.py`

## Security and privacy

- [ ] No new PHI reaches logs, error bodies, or telemetry
- [ ] Any new endpoint has authentication and authorisation-denial tests
- [ ] Any new SQL is parameterised
- [ ] Any schema change carries matching RLS policies and pgTAP coverage
- [ ] Any new dependency has been checked for known vulnerabilities

<!-- Touching db/migrations/, api/src/mivw_api/security/, or core/src/dicom/deid*
     requires two approvals. -->

## Documentation

- [ ] Docs updated in this PR
- [ ] ADR added if this is a non-trivial architectural decision

## Reviewer notes

<!-- Anything you want scrutinised, or known limitations you accepted. -->
