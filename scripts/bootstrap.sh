#!/usr/bin/env bash
# One command, everything up (PRD §16 Phase 1, item 8).
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { cp .env.example .env; echo "wrote .env — edit DATABASE_URL if you are using Supabase"; }

python3 -m pip install -e ".[dev]" --quiet
echo "package installed"

if grep -q "localhost:5432" .env 2>/dev/null; then
  if command -v docker >/dev/null; then
    docker compose up -d postgres
    until docker compose exec -T postgres pg_isready -U dev -d explainer >/dev/null 2>&1; do sleep 1; done
    echo "postgres ready"
  else
    echo "docker not found and DATABASE_URL points at localhost — start Postgres yourself" >&2
  fi
fi

explainer db init
explainer doctor
explainer verify
