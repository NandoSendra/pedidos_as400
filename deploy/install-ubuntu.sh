#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/pedidos_as400}"
APP_USER="${APP_USER:-pedidos}"

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Ejecuta este script como root: sudo ./deploy/install-ubuntu.sh"
    exit 1
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip rsync nginx

if ! id "$APP_USER" &>/dev/null; then
    useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

mkdir -p "$APP_DIR"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

if [[ ! -f "$APP_DIR/.env" ]]; then
    sudo -u "$APP_USER" cp "$APP_DIR/.env.example" "$APP_DIR/.env" 2>/dev/null || true
    echo "Crea $APP_DIR/.env con los valores de produccion antes de arrancar."
fi

sudo -u "$APP_USER" bash -c "
    cd '$APP_DIR'
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements-prod.txt
"

cp "$APP_DIR/deploy/pedidos-as400.service" /etc/systemd/system/pedidos-as400.service
systemctl daemon-reload
systemctl enable pedidos-as400

echo
echo "Instalacion base completada."
echo "1. Copia el codigo a $APP_DIR"
echo "2. Edita $APP_DIR/.env"
echo "3. Arranca: sudo systemctl start pedidos-as400"
echo "4. Opcional nginx: copia deploy/nginx-pedidos-as400.conf a /etc/nginx/sites-available/"
