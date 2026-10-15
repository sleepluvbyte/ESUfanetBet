"""Развёртывание бота на VPS с Windows.

Использование (PowerShell):

    $env:VPS_PASS="<пароль root>"
    $env:VPS_HOST="185.133.174.73"          # можно не указывать, есть по умолчанию
    python deploy\\deploy_from_windows.py            # полная установка
    python deploy\\deploy_from_windows.py update     # обновить код и перезапустить
    python deploy\\deploy_from_windows.py config     # залить только .env и account.json

Режим full:  полностью переустанавливает проект в /opt/esufanetbot
             (включая .env и account.json) и запускает systemd-сервис.
Режим update: заливает только код (без .env/account.json) и перезапускает сервис —
             так правки в .env на сервере не затираются.
Режим config: заливает .env и account.json (настройки) и перезапускает сервис.

Пароль не хранится в файле — читается из переменной окружения VPS_PASS.
"""

import io
import os
import pathlib
import socket
import sys
import zipfile

import paramiko

HOST = os.environ.get("VPS_HOST", "185.133.174.73")
USER = os.environ.get("VPS_USER", "root")
PASS = os.environ["VPS_PASS"]
PROJECT = pathlib.Path(__file__).resolve().parent.parent
APP_DIR = "/opt/esufanetbot"
SERVICE = "esufanetbot"
REMOTE_ZIP = "/root/esufanetbot.zip"

EXCLUDE_DIRS = {"venv", ".venv", "__pycache__", ".git", ".idea", ".vscode"}
EXCLUDE_SUFFIX = (".pyc", ".pyo", ".zip")
SECRET_FILES = {".env", "account.json"}


def build_zip(include_secrets: bool) -> bytes:
    buf = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(PROJECT):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for name in files:
                if name.endswith(EXCLUDE_SUFFIX):
                    continue
                if not include_secrets and name in SECRET_FILES:
                    continue
                full = pathlib.Path(root) / name
                rel = full.relative_to(PROJECT).as_posix()
                z.write(full, arcname=rel)
                count += 1
    data = buf.getvalue()
    print(f"Собрано файлов: {count}, размер {len(data) / 1024:.1f} КБ")
    return data


def run(ssh, cmd, check=True, timeout=900):
    print(f"\n$ {cmd}")
    _, stdout, _ = ssh.exec_command(cmd + " 2>&1", get_pty=False)
    chan = stdout.channel
    chan.settimeout(timeout)
    while True:
        try:
            data = chan.recv(8192)
        except socket.timeout:
            print("  (таймаут ожидания вывода)")
            break
        if not data:
            break
        sys.stdout.write(data.decode("utf-8", "replace"))
        sys.stdout.flush()
    code = chan.recv_exit_status()
    if check and code != 0:
        raise SystemExit(f"!! Команда завершилась с кодом {code}")
    return code


def upload(ssh, data):
    sftp = ssh.open_sftp()
    with sftp.open(REMOTE_ZIP, "wb") as fh:
        fh.write(data)
    sftp.close()
    print(f"Загружено в {REMOTE_ZIP}")


def upload_file(ssh, local_path, remote_path):
    sftp = ssh.open_sftp()
    sftp.put(str(local_path), remote_path)
    sftp.close()
    print(f"{local_path.name} -> {remote_path}")


def main():
    # Вывод сервера содержит юникод (●, эмодзи) — локальная консоль Windows
    # может быть cp1251, без этого падает UnicodeEncodeError.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    if mode not in ("full", "update", "config"):
        raise SystemExit("Режим: full | update | config")

    print(f"Подключаюсь к {HOST} (режим: {mode}) ...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        HOST, username=USER, password=PASS, timeout=30,
        banner_timeout=30, auth_timeout=30, look_for_keys=False, allow_agent=False,
    )
    print("Подключено.")

    if mode == "update":
        upload(ssh, build_zip(include_secrets=False))
        run(ssh, f"cd {APP_DIR} && (unzip -o {REMOTE_ZIP} || (apt-get install -y unzip && unzip -o {REMOTE_ZIP}))")
        run(ssh, f"sed -i 's/\\r$//' {APP_DIR}/deploy/*.sh")
        run(ssh, f"bash {APP_DIR}/deploy/update.sh")
    elif mode == "config":
        upload_file(ssh, PROJECT / ".env", f"{APP_DIR}/.env")
        if (PROJECT / "account.json").exists():
            upload_file(ssh, PROJECT / "account.json", f"{APP_DIR}/account.json")
        run(ssh, f"chown esubot:esubot {APP_DIR}/.env {APP_DIR}/account.json; chmod 600 {APP_DIR}/.env {APP_DIR}/account.json")
        run(ssh, f"systemctl restart {SERVICE}")
        run(ssh, "sleep 3; systemctl is-active " + SERVICE, check=False)
    else:
        run(ssh, "command -v python3 || echo NO_PYTHON3", check=False)
        tg = (
            "python3 -c \"import urllib.request as u; "
            "print('TELEGRAM_HTTP', u.urlopen('https://api.telegram.org', timeout=15).status)\""
        )
        if run(ssh, tg, check=False) != 0:
            print("\n!!! С сервера нет доступа к api.telegram.org — Telegram блокируется.")
            ssh.close()
            sys.exit(2)

        upload(ssh, build_zip(include_secrets=True))
        run(ssh, f"rm -rf {APP_DIR} && mkdir -p {APP_DIR}")
        run(ssh, f"cd {APP_DIR} && (unzip -o {REMOTE_ZIP} || (apt-get install -y unzip && unzip -o {REMOTE_ZIP}))")
        run(ssh, f"sed -i 's/\\r$//' {APP_DIR}/deploy/*.sh")
        run(ssh, f"bash {APP_DIR}/deploy/setup.sh")
        run(ssh, f"cd {APP_DIR} && ./venv/bin/python check_net.py", check=False)

    print("\n=== СТАТУС ===")
    run(ssh, f"systemctl is-enabled {SERVICE}; systemctl is-active {SERVICE}", check=False)
    print("\n=== ЛОГИ ===")
    run(ssh, f"journalctl -u {SERVICE} -n 30 --no-pager", check=False)

    ssh.close()
    print("\nГотово.")


if __name__ == "__main__":
    main()
