import re
from datetime import date as ddate
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import config

_SPACES = re.compile(r"\s+")

DATE_FORMATS = ("%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%Y")
TIME_FORMATS = ("%H:%M:%S", "%H:%M")

try:
    _TZ = ZoneInfo(config.TIMEZONE)
except Exception:
    _TZ = None


def now_local() -> datetime:
    """Текущее время в часовом поясе из .env (TIMEZONE).

    Нужно, чтобы напоминания и расписания работали верно на сервере (обычно UTC).
    """
    if _TZ is not None:
        return datetime.now(_TZ)
    return datetime.now()


def _attach(dt: datetime) -> datetime:
    return dt.replace(tzinfo=_TZ) if _TZ is not None else dt


# "Бесконечно далёкое" время того же часового пояса — для сортировок,
# где дата матча может отсутствовать (иначе naive/aware не сравнимы).
DT_MAX = _attach(datetime.max)
DT_MIN = _attach(datetime.min)


def normalize(value) -> str:
    """Нормализация текста для сравнения: trim, схлопывание пробелов, нижний регистр."""
    if value is None:
        return ""
    text = str(value).replace("\u00a0", " ").strip()
    text = _SPACES.sub(" ", text)
    return text.lower()


def clean(value) -> str:
    """Аккуратный текст для отображения/записи."""
    if value is None:
        return ""
    text = str(value).replace("\u00a0", " ").strip()
    return _SPACES.sub(" ", text)


def parse_match_datetime(date_val, time_val):
    """Возвращает datetime матча (в часовом поясе TIMEZONE) или None."""
    if date_val is None or time_val is None:
        return None

    if isinstance(date_val, datetime):
        day = date_val.date()
    elif isinstance(date_val, ddate):
        day = date_val
    else:
        text = clean(date_val)
        if not text:
            return None
        day = None
        for fmt in DATE_FORMATS:
            try:
                day = datetime.strptime(text, fmt).date()
                break
            except ValueError:
                continue
        if day is None:
            # Иногда дата приходит с временем: "15/10/2026 13:37"
            for fmt in ("%d/%m/%Y %H:%M", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M"):
                try:
                    return _attach(datetime.strptime(text, fmt))
                except ValueError:
                    continue
            return None

    if isinstance(time_val, datetime):
        moment = time_val.time()
    elif isinstance(time_val, dtime):
        moment = time_val
    else:
        text = clean(time_val)
        moment = None
        for fmt in TIME_FORMATS:
            try:
                moment = datetime.strptime(text, fmt).time()
                break
            except ValueError:
                continue
        if moment is None:
            return None

    return _attach(datetime.combine(day, moment))


def format_dt(moment: datetime) -> str:
    return moment.strftime("%d.%m.%Y %H:%M")
