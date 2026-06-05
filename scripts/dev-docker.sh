#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
    cp .env.example .env
    echo "Creado .env desde .env.example"
fi

docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
