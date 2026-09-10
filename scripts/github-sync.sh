#!/usr/bin/env bash
#
# Prepare and perform the first synchronisation with a public GitHub repository.
#
# Publishing a medical imaging codebase is one-way: once history is public it
# cannot be recalled. This script runs the pre-flight checks first and only
# pushes after you confirm.
#
# Usage:
#   scripts/github-sync.sh check                       # audit only, no network
#   scripts/github-sync.sh init  git@github.com:you/repo.git
#   scripts/github-sync.sh push

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

info() { printf '\033[0;36m==>\033[0m %s\n' "$1"; }
ok()   { printf '\033[0;32m ok \033[0m %s\n' "$1"; }
warn() { printf '\033[0;33m !! \033[0m %s\n' "$1"; }
bad()  { printf '\033[0;31m xx \033[0m %s\n' "$1" >&2; }

FAILURES=0
note_failure() { bad "$1"; FAILURES=$((FAILURES + 1)); }

# --------------------------------------------------------------------- checks
check_history() {
  info "Auditing repository history before publication"

  # 1. Secrets ---------------------------------------------------------------
  if command -v gitleaks >/dev/null 2>&1; then
    if gitleaks detect --no-banner --redact --log-opts="--all" >/dev/null 2>&1; then
      ok "gitleaks found no secrets in history"
    else
      note_failure "gitleaks found potential secrets. Do NOT push; scrub history first."
    fi
  else
    warn "gitleaks not installed; skipping secret scan (install before publishing)"
  fi

  # 2. Patient data ----------------------------------------------------------
  local dicom
  dicom="$(git log --all --diff-filter=A --name-only --pretty=format: \
           | grep -E '\.dcm$' | sort -u || true)"
  if [[ -z "$dicom" ]]; then
    ok "no DICOM files anywhere in history"
  else
    bad "DICOM files present in history:"
    printf '      %s\n' $dicom
    note_failure "verify every one is synthetic before publishing"
  fi

  # 3. Environment files and key material ------------------------------------
  # .env.example is a committed template of variable *names*; real values live
  # in the git-ignored .env.local.
  local sensitive
  sensitive="$(git log --all --diff-filter=A --name-only --pretty=format: \
               | grep -E '(^|/)\.env($|\.local$|\.production$)|\.pem$|\.key$|\.p12$|\.pfx$|id_rsa' \
               | sort -u || true)"
  if [[ -z "$sensitive" ]]; then
    ok "no environment files or key material in history"
  else
    bad "sensitive files in history:"
    printf '      %s\n' $sensitive
    note_failure "these must be removed from history, not just from HEAD"
  fi

  # 4. Working tree ----------------------------------------------------------
  if [[ -z "$(git status --porcelain)" ]]; then
    ok "working tree is clean"
  else
    warn "working tree has uncommitted changes; they will not be pushed"
  fi

  # 5. Required public-facing files -----------------------------------------
  local required=(README.md LICENSE SECURITY.md CONTRIBUTING.md .gitignore)
  for f in "${required[@]}"; do
    [[ -f "$f" ]] && ok "present: $f" || note_failure "missing: $f"
  done

  # 6. Research-use disclaimer ----------------------------------------------
  if grep -qi 'research use only' README.md; then
    ok "README carries the research-use-only disclaimer"
  else
    note_failure "README must state the research-use-only status prominently"
  fi

  # 7. Large files -----------------------------------------------------------
  local large
  large="$(git ls-files -z | xargs -0 -r du -k 2>/dev/null \
           | awk '$1 > 5120 {print $2 " (" int($1/1024) " MB)"}' || true)"
  if [[ -z "$large" ]]; then
    ok "no tracked file exceeds 5 MB"
  else
    warn "large files tracked without LFS:"
    printf '      %s\n' "$large"
  fi

  echo
  if (( FAILURES > 0 )); then
    bad "$FAILURES blocking issue(s). Resolve before publishing."
    return 1
  fi
  ok "pre-flight checks passed"
}

# ----------------------------------------------------------------------- init
init_remote() {
  local url="${1:-}"
  [[ -n "$url" ]] || { bad "usage: $0 init <git-remote-url>"; exit 2; }

  if git remote get-url origin >/dev/null 2>&1; then
    warn "origin already set to $(git remote get-url origin); updating"
    git remote set-url origin "$url"
  else
    git remote add origin "$url"
  fi
  ok "origin -> $url"

  if command -v git-lfs >/dev/null 2>&1; then
    git lfs install --local
    ok "git-lfs initialised (.gitattributes already tracks .dcm, .onnx and golden PNGs)"
  else
    warn "git-lfs not installed. Install it before adding binary fixtures:"
    warn "  sudo apt-get install git-lfs   # or: brew install git-lfs"
  fi
}

# ----------------------------------------------------------------------- push
push_repo() {
  git remote get-url origin >/dev/null 2>&1 || {
    bad "no origin configured; run: $0 init <git-remote-url>"; exit 2;
  }

  check_history || { bad "refusing to push"; exit 1; }

  echo
  info "About to push to: $(git remote get-url origin)"
  info "Branch: $(git branch --show-current)"
  info "Commits: $(git rev-list --count HEAD)"
  echo
  read -r -p "This publishes the repository. Type 'publish' to continue: " confirm
  [[ "$confirm" == "publish" ]] || { warn "aborted"; exit 1; }

  git push -u origin "$(git branch --show-current)"
  ok "pushed"

  cat <<'EOF'

Now configure the repository on GitHub:

  Settings -> General
    - Disable wiki and projects unless you intend to use them

  Settings -> Branches -> add rule for 'main'
    - Require a pull request before merging (1 approval; 2 for the paths in
      CODEOWNERS covering migrations, security and de-identification)
    - Require status checks: lint, database, core, api, frontend, codeql
    - Require branches to be up to date before merging
    - Require conversation resolution
    - Do not allow force pushes or deletions

  Settings -> Code security
    - Enable Dependabot alerts and security updates
    - Enable secret scanning and push protection
    - Enable private vulnerability reporting (SECURITY.md depends on it)

  Settings -> Actions -> General
    - Workflow permissions: read-only by default
    - Require approval for all outside collaborators

  Add repository secrets only when you reach the release workflow:
    MAC_CERT_P12, MAC_CERT_PASSWORD, APPLE_ID, APPLE_APP_PASSWORD,
    APPLE_TEAM_ID, WIN_CERT_PFX, WIN_CERT_PASSWORD
EOF
}

case "${1:-check}" in
  check) check_history ;;
  init)  init_remote "${2:-}" ;;
  push)  push_repo ;;
  *)     bad "usage: $0 {check|init <url>|push}"; exit 2 ;;
esac
