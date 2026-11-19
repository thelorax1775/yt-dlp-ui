#!/usr/bin/env bash
unset PYTHONPATH PYTHONHOME VIRTUAL_ENV
set -euo pipefail

# Single entry point for the project's checks. CI runs exactly this script.
#   ./check.sh            backend, then frontend
#   ./check.sh backend    install backend deps into backend/.venv, run pytest
#   ./check.sh frontend   npm ci, type check, lint, production build

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

check_backend() {
  echo "==> backend: install dependencies into backend/.venv"
  cd "$ROOT/backend"
  if command -v uv >/dev/null 2>&1; then
    [ -x .venv/bin/python ] || uv venv --python "${CHECK_PYTHON:-3.12}" .venv
    uv pip install --quiet --python .venv/bin/python \
      -r requirements.txt -r requirements-dev.txt
  else
    [ -x .venv/bin/python ] || python3 -m venv .venv
    .venv/bin/python -m pip install --quiet --disable-pip-version-check \
      -r requirements.txt -r requirements-dev.txt
  fi
  echo "==> backend: pytest"
  .venv/bin/python -m pytest
}

check_frontend() {
  cd "$ROOT/frontend"
  export NEXT_TELEMETRY_DISABLED=1
  echo "==> frontend: npm ci"
  npm ci --no-audit --no-fund
  echo "==> frontend: type check"
  npx tsc --noEmit
  echo "==> frontend: lint"
  npm run lint
  echo "==> frontend: build"
  npm run build
}

case "${1:-all}" in
  backend) check_backend ;;
  frontend) check_frontend ;;
  all)
    check_backend
    check_frontend
    ;;
  *)
    echo "usage: $0 [backend|frontend]" >&2
    exit 2
    ;;
esac

echo "==> checks passed"
