#!/usr/bin/env bash
# Установка бота на Ubuntu/Debian VPS.
# Запуск из корня проекта:  bash deploy/setup.sh
# (sudo не обязателен, если ты уже root)
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/esufanetbot}"
SERVICE_NAME="esufanetbot"
RUN_USER="esubot"

if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi

export DEBIAN_FRONTEND=noninteractive
echo "==> Обновление пакетов и установка Python"
$SUDO apt-get update -y
$SUDO apt-get install -y python3 python3-venv python3-pip rsync unzip

echo "==> Создание пользователя $RUN_USER (если нет)"
if ! id "$RUN_USER" >/dev/null 2>&1; then
  $SUDO useradd --system --create-home --shell /usr/sbin/nologin "$RUN_USER"
fi

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$SRC_DIR" != "$APP_DIR" ]; then
  echo "==> Копирование проекта в $APP_DIR"
  $SUDO mkdir -p "$APP_DIR"
  $SUDO rsync -a --delete --exclude venv --exclude __pycache__ \
    "$SRC_DIR"/ "$APP_DIR"/
fi

cd "$APP_DIR"

echo "==> Виртуальное окружение и зависимости"
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

echo "==> Права доступа"
$SUDO chown -R "$RUN_USER":"$RUN_USER" "$APP_DIR"
$SUDO chmod 600 "$APP_DIR/.env" "$APP_DIR/account.json" 2>/dev/null || true

echo "==> Установка systemd-сервиса"
$SUDO cp "$APP_DIR/deploy/esufanetbot.service" "/etc/systemd/system/${SERVICE_NAME}.service"
$SUDO sed -i "s|__APP_DIR__|$APP_DIR|g; s|__RUN_USER__|$RUN_USER|g" \
  "/etc/systemd/system/${SERVICE_NAME}.service"
$SUDO systemctl daemon-reload
$SUDO systemctl enable --now "${SERVICE_NAME}"

echo "==> Статус"
$SUDO systemctl status "${SERVICE_NAME}" --no-pager || true
echo
echo "Готово. Логи:  journalctl -u ${SERVICE_NAME} -f"
