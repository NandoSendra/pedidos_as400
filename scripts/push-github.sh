#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "Subir a https://github.com/NandoSendra/pedidos_as400"
echo ""
echo "Necesitas un token de GitHub con permiso 'repo':"
echo "  https://github.com/settings/tokens"
echo ""
read -rsp "Pega el token (no se muestra): " TOKEN
echo ""

if [[ -z "$TOKEN" ]]; then
    echo "Token vacio. Cancelado."
    exit 1
fi

git -c credential.helper= push "https://NandoSendra:${TOKEN}@github.com/NandoSendra/pedidos_as400.git" main
git branch --set-upstream-to=origin/main main 2>/dev/null || true

echo ""
echo "Listo. Codigo subido a GitHub."
