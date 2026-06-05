#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"

if [[ ! -f .env ]]; then
    echo "Falta .env. Copia .env.example y configuralo:"
    echo "  cp .env.example .env"
    exit 1
fi

git pull --ff-only
docker compose build
docker compose up -d
docker compose ps
