# Real-Time AI-Powered Medical Image Workstation (MIVW)

> **RESEARCH USE ONLY.** This software is **not** a cleared or approved medical device.
> It must not be used for primary diagnosis, treatment planning, or any clinical
> decision-making. See [docs/06-security-compliance.md](docs/06-security-compliance.md).

A GPU-accelerated workstation for interactive visualisation and AI-assisted analysis of
volumetric medical imaging (CT / MR / PET), built as a five-layer system:

| Layer | Technology | Directory |
| --- | --- | --- |
| Presentation | Electron + TypeScript + Vue 3 + Quasar | [`desktop/`](desktop/) |
| API gateway | Python 3.12 + FastAPI + Pydantic v2 | [`api/`](api/) |
| Compute core | C++20 + CUDA 12 + TensorRT + DCMTK | [`core/`](core/) |
| Rendering | Vulkan 1.3 + SPIR-V compute/graphics shaders | [`core/vulkan/`](core/vulkan/) |
| Data | PostgreSQL 16 (RLS + pgcrypto) + S3/MinIO object store | [`db/`](db/) |

## Deployment modes

A single build supports both topologies, selected by `MIVW_MODE`:

- **`local`** — everything on one GPU workstation. Loopback-only binding, OS-keychain
  credentials, no TLS termination required.
- **`server`** — Electron thin client talks to a remote GPU render/inference node over
  mTLS. Frames are streamed; pixel data never lands on the client disk.

## Quick start

```bash
git clone <repo> && cd RealTimeAIPoweredMedicalImageWorkstation
./scripts/bootstrap.sh          # toolchain + pre-commit hooks
docker compose -f infra/docker-compose.yml up -d   # PostgreSQL 16 + MinIO
make db-migrate
## in case the above command fails, try running the following command individually:
##     export MIVW_DB_DSN='postgresql://postgres:devonly_not_for_deployment@127.0.0.1:5434/mivw', then re-run the above command.
make core                       # CMake + CUDA build -> Python extension
make api                        # uvicorn on 127.0.0.1:8000
make desktop                    # Quasar dev server + Electron shell
```

Full setup instructions: [docs/08-dev-environment.md](docs/08-dev-environment.md).

## Documentation

| Document | Purpose |
| --- | --- |
| [01 Architecture](docs/01-architecture.md) | System design, data flow, ADRs |
| [02 Components](docs/02-components.md) | Per-module responsibilities and interfaces |
| [03 Data model](docs/03-data-model.md) | Schema, RLS, encryption, migrations |
| [04 API contract](docs/04-api-contract.md) | REST + WebSocket surface |
| [05 Testing strategy](docs/05-testing-strategy.md) | Test pyramid and tooling |
| [06 Security & compliance](docs/06-security-compliance.md) | Threat model, HIPAA/GDPR controls |
| [07 Sprint plan](docs/07-sprint-plan.md) | 12-sprint delivery plan |
| [08 Dev environment](docs/08-dev-environment.md) | Toolchain, CI/CD, build matrix |

## Testing

```bash
make test-db        # pgTAP against an ephemeral Testcontainers PostgreSQL
make test-core      # GoogleTest + CTest + compute-sanitizer
make test-api       # pytest + Schemathesis contract fuzzing
make test-unit      # Vitest
make test-component # Storybook interaction tests
make test-e2e       # Playwright driving the Electron binary
```

## Licence

See [LICENSE](LICENSE). Third-party notices in [docs/THIRD-PARTY.md](docs/THIRD-PARTY.md).
