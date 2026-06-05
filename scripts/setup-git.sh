#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -d .git ]]; then
    echo "Ya existe un repositorio git aqui."
    git status -sb
    exit 0
fi

git init -b main
git add .
git status

cat <<'EOF'

Siguiente paso en GitHub:
  1. Crea un repo nuevo (vacío, sin README): https://github.com/new
  2. Enlazalo y sube el codigo:

     git remote add origin https://github.com/TU-USUARIO/pedidos_as400.git
     git commit -m "Initial commit"
     git push -u origin main

En el Ubuntu (una sola vez):
  git clone https://github.com/TU-USUARIO/pedidos_as400.git
  cd pedidos_as400
  cp .env.example .env && nano .env
  docker compose up -d --build

Deploy automatico (opcional):
  Instala un runner self-hosted en Ubuntu siguiendo:
  https://github.com/TU-USUARIO/pedidos_as400/settings/actions/runners/new

EOF
