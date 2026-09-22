SHELL := /bin/bash
.DEFAULT_GOAL := help

VENV        ?= .venv
PY          ?= $(VENV)/bin/python
UV          ?= uv
DESKTOP_TMP ?= $(HOME)/.cache/mivw-desktop
CMAKE_PRESET?= dev
BUILD_DIR   ?= core/build/$(CMAKE_PRESET)
COMPOSE     ?= docker compose -f infra/docker-compose.yml

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- environment
.PHONY: bootstrap up down
bootstrap: ## Install toolchain, hooks and dependencies
	./scripts/bootstrap.sh

up: ## Start PostgreSQL, MinIO and the mock OIDC provider
	$(COMPOSE) up -d

down: ## Stop the local stack
	$(COMPOSE) down

# ---------------------------------------------------------------- database
.PHONY: db-migrate db-seed db-reset
db-migrate: ## Apply forward-only migrations
	$(PY) scripts/migrate.py apply

db-seed: ## Load synthetic, non-PHI development fixtures
	$(PY) scripts/migrate.py seed

db-reset: ## Drop and rebuild the development database
	$(COMPOSE) exec -T postgres psql -U postgres -c "DROP DATABASE IF EXISTS mivw;"
	$(COMPOSE) exec -T postgres psql -U postgres -c "CREATE DATABASE mivw;"
	$(MAKE) db-migrate db-seed

# ---------------------------------------------------------------- core (C++)
.PHONY: core core-configure shaders
core-configure: ## Configure CMake for $(CMAKE_PRESET)
	cmake --preset $(CMAKE_PRESET) -S core

core: core-configure ## Build the C++/CUDA core and install mivw_core
	cmake --build $(BUILD_DIR) --parallel
	$(UV) pip install -e core

shaders: ## Compile GLSL to SPIR-V
	./scripts/compile_shaders.sh

# ---------------------------------------------------------------- api
.PHONY: api openapi api-client
api: ## Run the FastAPI gateway with reload
	$(VENV)/bin/uvicorn mivw_api.main:create_app --factory --host 127.0.0.1 --port 8000 --reload

openapi: ## Export the OpenAPI document
	$(PY) scripts/export_openapi.py > openapi.json

api-client: openapi ## Regenerate the typed TypeScript client
	cd desktop && npm run generate:client

# ---------------------------------------------------------------- desktop
.PHONY: desktop storybook
desktop: ## Run Quasar dev server inside Electron
	mkdir -p "$(DESKTOP_TMP)"
	TMPDIR="$(DESKTOP_TMP)" cd desktop && TMPDIR="$(DESKTOP_TMP)" npm run dev

storybook: ## Run Storybook
	cd desktop && npm run storybook

# ---------------------------------------------------------------- tests
.PHONY: test test-db test-core test-api test-unit test-component test-e2e
test: test-db test-core test-api test-unit test-component ## Run everything except E2E

test-db: ## pgTAP suites against an ephemeral PostgreSQL
	docker build -t mivw-postgres-pgtap -f infra/postgres-test.Dockerfile .
	env -u MIVW_DB_DSN MIVW_TEST_POSTGRES_IMAGE=mivw-postgres-pgtap $(PY) -m pytest db/tests -v

test-core: ## GoogleTest via CTest
	ctest --test-dir $(BUILD_DIR) --output-on-failure

test-api: ## pytest + contract fuzzing
	cd api && ../$(PY) -m pytest tests -v --cov=mivw_api --cov-fail-under=85

test-unit: ## Vitest
	cd desktop && npm run test:unit

test-component: ## Storybook interaction + a11y tests
	cd desktop && npm run build-storybook
	cd desktop && { \
		if curl -fsS http://127.0.0.1:6006/index.json >/dev/null 2>&1; then \
			echo "A server is already responding on port 6006; stop it before running component tests"; \
			exit 1; \
		fi; \
		python3 -m http.server 6006 --bind 127.0.0.1 --directory storybook-static >/dev/null 2>&1 & \
		server_pid=$$!; \
		trap 'kill "$$server_pid" 2>/dev/null || true; wait "$$server_pid" 2>/dev/null || true' EXIT; \
		for attempt in {1..30}; do \
			if ! kill -0 "$$server_pid" 2>/dev/null; then \
				echo "Storybook static server exited before becoming ready"; \
				exit 1; \
			fi; \
			if curl -fsS http://127.0.0.1:6006/index.json >/dev/null 2>&1; then break; fi; \
			sleep 1; \
		done; \
		curl -fsS http://127.0.0.1:6006/index.json >/dev/null || { \
			echo "Storybook static server did not become ready on port 6006"; \
			exit 1; \
		}; \
		npm run test:component; \
	}

test-e2e: ## Playwright driving Electron
	cd desktop && npm run test:e2e

# ---------------------------------------------------------------- quality
.PHONY: lint format audit
lint: ## Run all linters
	$(VENV)/bin/ruff check api scripts
	$(VENV)/bin/mypy --strict api/src
	$(VENV)/bin/sqlfluff lint db
	cd desktop && npm run lint
	cmake --build --preset $(CMAKE_PRESET) --target clang-tidy

format: ## Apply all formatters
	$(VENV)/bin/ruff format api scripts
	cd desktop && npm run format
	find core -name '*.cpp' -o -name '*.hpp' -o -name '*.cu' | xargs clang-format -i

audit: ## Dependency and secret scanning
	$(VENV)/bin/pip-audit
	cd desktop && npm audit --audit-level=high
	gitleaks detect --no-banner

# ---------------------------------------------------------------- aggregate
.PHONY: all clean
all: core api-client ## Build every layer

clean: ## Remove build artefacts
	rm -rf core/build desktop/dist desktop/.quasar openapi.json
