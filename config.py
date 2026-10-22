import os
import re
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _split_list(value: str):
    return [item.strip() for item in re.split(r"[,\n;]+", value or "") if item.strip()]


def _parse_admin_ids(value: str):
    result = set()
    for item in _split_list(value):
        if item.isdigit():
            result.add(int(item))
    return result


BOT_TOKEN = os.getenv("TELEGRAMM_TOKEN", "").strip()
SPREADSHEET_ID = os.getenv("GS_SHEETS", "").strip()
GOOGLE_CREDENTIALS = str(
    BASE_DIR / os.getenv("GOOGLE_CREDENTIALS", "account.json")
)

# Прокси для доступа к Telegram, если API заблокирован сетью.
# Примеры: http://user:pass@host:8080  или  socks5://user:pass@host:1080
PROXY_URL = os.getenv("PROXY_URL", "").strip()

ADMIN_IDS = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))

# Филиалы/регионы компании (кнопки при регистрации)
DEFAULT_BRANCHES = [
    "Уфа",
    "Стерлитамак",
    "Октябрьский",
    "Туймазы",
    "Нефтекамск",
    "Оренбург",
    "Омск",
    "Смоленск",
    "Калининград",
]
BRANCHES = _split_list(os.getenv("BRANCHES", "")) or DEFAULT_BRANCHES

# Названия листов в Google Sheets
SHEET_MATCHES = os.getenv("SHEET_MATCHES", "Матчи")
SHEET_USERS = os.getenv("SHEET_USERS", "Участники")
SHEET_PREDICTIONS = os.getenv("SHEET_PREDICTIONS", "Прогнозы")
SHEET_RESULTS = os.getenv("SHEET_RESULTS", "Итоги")
SHEET_DRAW = os.getenv("SHEET_DRAW", "Розыгрыш")
SHEET_SCORES = os.getenv("SHEET_SCORES", "Баллы")

# Этапы турнира
STAGES = [
    "Отборочный",
    "Полуфинал",
    "Финал онлайн",
    "Финал оффлайн",
]

TIMEZONE = os.getenv("TIMEZONE", "Asia/Yekaterinburg")
REMINDER_MINUTES = int(os.getenv("REMINDER_MINUTES", "120"))
DRAW_THRESHOLD = float(os.getenv("DRAW_THRESHOLD", "0.7"))

# Лимиты длины вводимого текста (защита от раздувания сообщений и таблицы)
FIO_MAX = 100
TEAM_MAX = 60
