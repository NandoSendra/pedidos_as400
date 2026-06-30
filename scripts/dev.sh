#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -d venv ]]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements-prod.txt

if [[ ! -f .env ]]; then
    cp .env.example .env
    echo "Creado .env desde .env.example. Revisa los valores antes de continuar."
fi

if [[ ! -f asientos_ejemplos.json && -f asientos_ejemplos.json.example ]]; then
    cp asientos_ejemplos.json.example asientos_ejemplos.json
    echo "Creado asientos_ejemplos.json desde asientos_ejemplos.json.example."
fi

export FLASK_DEBUG="${FLASK_DEBUG:-true}"

echo "Desarrollo en http://127.0.0.1:${FLASK_PORT:-5100}/pedido"
python app.py
