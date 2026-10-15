#!/usr/bin/env bash
# Обновление бота после изменения файлов:  bash deploy/update.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/esufanetbot}"
SERVICE_NAME="esufanetbot"

if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi

cd "$APP_DIR"
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
$SUDO systemctl restart "${SERVICE_NAME}"
sleep 2
$SUDO systemctl status "${SERVICE_NAME}" --no-pager || true
