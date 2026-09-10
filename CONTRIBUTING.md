# Contributing

## The one rule that matters

**Never commit real patient data.** Not in fixtures, not in issues, not in screenshots,
not in test logs. Generate synthetic cases with:

```bash
python3 scripts/make_fixtures.py --output core/tests/fixtures/generated
```

A pre-commit hook rejects any `.dcm` file the generator did not produce. If you ever
suspect PHI reached a branch, stop and contact the maintainers before pushing — history
rewriting is far cheaper before a push than after.

## Getting set up

```bash
./scripts/bootstrap.sh
docker compose -f infra/docker-compose.yml up -d
make db-migrate db-seed
make all
```

Details in [docs/08-dev-environment.md](docs/08-dev-environment.md).

## Workflow

Trunk-based. Branch off `main`, keep it short-lived, squash-merge.

1. `git switch -c feat/oblique-reformat`
2. Make the change **with its tests** — test work is inside the story, never a follow-up ticket
3. `make lint && make test`
4. Open a PR; fill in the template
5. Address review; squash-merge

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/), enforced by a commit-msg hook:

```
feat(render): add oblique reformat to the MPR pane
fix(api): return 404 instead of 403 for cross-tenant studies
feat(db)!: drop the legacy annotation payload column
```

Types: `build`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`, `revert`,
`style`, `test`.

## Where tests go

Write the regression test at the **lowest layer that can reproduce the bug**. E2E specs
cover user journeys, not edge cases.

| Change | Required tests |
| --- | --- |
| Schema or RLS policy | pgTAP, including a cross-tenant negative case |
| C++/CUDA | GoogleTest; GPU kernels compared against a CPU reference |
| Renderer | Golden image with SSIM tolerance, not exact match |
| API endpoint | pytest including unauthenticated and insufficient-role cases |
| Store or composable | Vitest |
| Component | Storybook story set: default, loading, empty, error, plus a `play` function |
| User journey | Playwright |

Full strategy: [docs/05-testing-strategy.md](docs/05-testing-strategy.md).

## Definition of Done

- Tests cover new logic at the lowest applicable layer
- New components have stories including error and empty states
- New endpoints have authorisation-denial tests
- Schema changes have pgTAP coverage
- Coverage gates hold (85 % API, 80 % core and frontend)
- Documentation updated in the same PR
- No new SAST or dependency findings

## Areas requiring two approvals

A mistake in these becomes a PHI incident rather than a bug:

- `db/migrations/` — RLS policies and grants
- `api/src/mivw_api/security/` — authentication and authorisation
- `core/src/dicom/deid*` — de-identification

## Architecture decisions

Non-trivial technical decisions get an ADR in [docs/adr/](docs/adr/). Copy the format of
an existing one: context, decision, consequences (positive *and* negative), alternatives
rejected. Recording why an option was rejected is the part future readers need most.

## Code style

Everything is enforced by pre-commit, so run `make format` rather than arguing with a
linter. C++ follows the Core Guidelines with `clang-tidy`; Python is `ruff` plus
`mypy --strict`; TypeScript is `eslint` with typescript-eslint strict rules.

Comments explain *why*, not *what*. If a line needs a comment to say what it does,
rename something instead.
