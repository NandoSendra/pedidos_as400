#!/usr/bin/env bash
set -euo pipefail

# Uso:
#   cp deploy/local.env.example deploy/local.env
#   ./scripts/sync-to-ubuntu.sh
#
# O bien:
#   export DEPLOY_HOST=usuario@ip-publica-ubuntu
#   ./scripts/sync-to-ubuntu.sh

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -f "$ROOT_DIR/deploy/local.env" ]]; then
    # shellcheck disable=SC1091
    source "$ROOT_DIR/deploy/local.env"
fi

DEPLOY_HOST="${DEPLOY_HOST:?Define DEPLOY_HOST en deploy/local.env o en el entorno}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/pedidos_as400}"
DEPLOY_SSH_PORT="${DEPLOY_SSH_PORT:-22}"

SSH_OPTS=(-p "$DEPLOY_SSH_PORT")
RSYNC_SSH="ssh -p $DEPLOY_SSH_PORT"

rsync -avz --delete -e "$RSYNC_SSH" \
    --exclude venv \
    --exclude .env \
    --exclude deploy/local.env \
    --exclude __pycache__ \
    --exclude .DS_Store \
    --exclude "*.pyc" \
    "$ROOT_DIR/" "$DEPLOY_HOST:$DEPLOY_PATH/"

ssh "${SSH_OPTS[@]}" "$DEPLOY_HOST" "cd '$DEPLOY_PATH' && ./deploy/update.sh"

echo "Despliegue sincronizado en $DEPLOY_HOST:$DEPLOY_PATH"
