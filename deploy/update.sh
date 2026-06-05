#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"

if [[ ! -d venv ]]; then
    python3 -m venv venv
fi

./venv/bin/pip install -r requirements-prod.txt

if command -v systemctl &>/dev/null && systemctl list-unit-files | grep -q pedidos-as400.service; then
    sudo systemctl restart pedidos-as400
    sudo systemctl status pedidos-as400 --no-pager
else
    echo "Servicio systemd no encontrado. Reinicia gunicorn manualmente."
fi
