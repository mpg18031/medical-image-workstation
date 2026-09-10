#!/usr/bin/env bash
#
# Prepares a development machine. Idempotent: safe to re-run.
# Never writes secrets into the repository.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

info()  { printf '\033[0;36m==>\033[0m %s\n' "$1"; }
warn()  { printf '\033[0;33m!!\033[0m %s\n' "$1"; }
fail()  { printf '\033[0;31mxx\033[0m %s\n' "$1" >&2; exit 1; }

require() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required tool: $1 ($2)"
}

# ------------------------------------------------------------------ toolchain
info "Checking required tooling"
require cmake  "https://cmake.org/download/"
require ninja  "install ninja-build"
require git    "https://git-scm.com/"
require docker "https://docs.docker.com/get-docker/"
require node   "Node.js 20 LTS"
require python3 "Python 3.12"

NODE_MAJOR="$(node --version | sed 's/^v\([0-9]*\).*/\1/')"
[[ "$NODE_MAJOR" -ge 20 ]] || fail "Node.js 20 or newer required (found $(node --version))"

PY_MINOR="$(python3 -c 'import sys; print(sys.version_info.minor)')"
[[ "$PY_MINOR" -ge 12 ]] || fail "Python 3.12 or newer required"

if ! command -v glslc >/dev/null 2>&1; then
  fail "Vulkan SDK not on PATH (glslc missing): https://vulkan.lunarg.com/sdk/home"
fi

if command -v nvcc >/dev/null 2>&1; then
  info "CUDA found: $(nvcc --version | tail -1)"
else
  warn "CUDA toolkit not found. Building CPU-only; TensorRT inference unavailable."
fi

# ------------------------------------------------------------------- python
info "Setting up the Python environment"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
UV_BIN="$(command -v uv || true)"
[[ -x "$UV_BIN" ]] || fail "uv installation completed but uv is not available on PATH"
"$UV_BIN" venv --python 3.12 .venv
"$UV_BIN" pip install --python .venv -e "./api[dev]"
"$UV_BIN" pip install --python .venv "numpy>=1.26" "pydicom>=3.0"

# Auto-export MIVW_DB_DSN (from .env.local, falling back to the docker-compose
# default) whenever .venv is activated, so scripts/migrate.py, db/tests, etc.
# work without manually exporting it every session.
ACTIVATE_HOOK='
# --- mivw: auto-export MIVW_DB_DSN on activation (added by scripts/bootstrap.sh) ---
if [[ -f "$VIRTUAL_ENV/../.env.local" ]]; then
  export MIVW_DB_DSN="$(grep -m1 "^MIVW_DB_DSN=" "$VIRTUAL_ENV/../.env.local" | cut -d= -f2-)"
else
  export MIVW_DB_DSN="postgresql://mivw_service:devonly_not_for_deployment@localhost:5434/mivw"
fi
# --- end mivw hook ---'
if ! grep -q "mivw: auto-export MIVW_DB_DSN" .venv/bin/activate; then
  printf '%s\n' "$ACTIVATE_HOOK" >> .venv/bin/activate
fi

# --------------------------------------------------------------------- node
info "Installing frontend dependencies"
npm ci --prefix desktop
npx --prefix desktop playwright install --with-deps

# --------------------------------------------------------------- git hooks
info "Installing pre-commit hooks"
"$UV_BIN" pip install --python .venv pre-commit
.venv/bin/pre-commit install --install-hooks
.venv/bin/pre-commit install --hook-type commit-msg

# ---------------------------------------------------------- local config
if [[ ! -f .env.local ]]; then
  info "Creating .env.local from .env.example"
  cp .env.example .env.local
  warn "Fill in .env.local before running the API. It is git-ignored; keep it that way."
else
  info ".env.local already exists; leaving it untouched"
fi

# ------------------------------------------------------- dev certificates
if [[ ! -f infra/certs/dev-cert.pem ]]; then
  info "Generating self-signed development certificates"
  mkdir -p infra/certs
  openssl req -x509 -newkey rsa:4096 -sha256 -days 365 -nodes \
    -keyout infra/certs/dev-key.pem \
    -out infra/certs/dev-cert.pem \
    -subj "/CN=localhost/O=MIVW Development" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" 2>/dev/null
  chmod 600 infra/certs/dev-key.pem
  warn "Development certificates only. Never use these outside a local machine."
fi

# --------------------------------------------------------------- fixtures
info "Generating synthetic test fixtures"
.venv/bin/python scripts/make_fixtures.py --output core/tests/fixtures/generated

cat <<'EOF'

Bootstrap complete.

  1. docker compose -f infra/docker-compose.yml up -d
  2. make db-migrate db-seed
  3. make core
  4. make api        (in one terminal)
  5. make desktop    (in another)

Reminder: this project is RESEARCH USE ONLY and must never be pointed at a
production PACS or given real patient data.
EOF
