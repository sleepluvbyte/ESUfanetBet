import html
import re
from datetime import date as ddate
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import config

_SPACES = re.compile(r"\s+")

# Управляющие, невидимые и bidi-символы: их можно использовать для визуального
# спуфинга в сообщениях или чтобы «сломать» дедуп по ФИО.
_INVISIBLE = re.compile(
    "[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f"
    "\u200b-\u200f\u2028\u2029\ufeff\u202a-\u202e\u2066-\u2069]"
)

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
    text = strip_invisible(str(value)).replace("\u00a0", " ").strip()
    text = _SPACES.sub(" ", text)
    return text.lower()


def clean(value) -> str:
    """Аккуратный текст для отображения/записи."""
    if value is None:
        return ""
    text = str(value).replace("\u00a0", " ").strip()
    return _SPACES.sub(" ", text)


def strip_invisible(value) -> str:
    """Убирает управляющие, невидимые и bidi-символы (защита от спуфинга)."""
    return _INVISIBLE.sub("", str(value if value is not None else ""))


def sanitize(value, max_len=0) -> str:
    """Очистка пользовательского текста: пробелы, невидимые символы, лимит длины.

    Порядок важен: сначала clean() (схлопывает в т.ч. переводы строк в пробел),
    затем удаляем невидимые символы, затем обрезаем до max_len.
    """
    text = strip_invisible(clean(value))
    if max_len and len(text) > max_len:
        text = text[:max_len].rstrip()
    return text


def esc(value) -> str:
    """Экранирование для Telegram (parse_mode=HTML).

    Обязательно применять к любому пользовательскому/админскому тексту,
    который попадает в сообщение: иначе возможна HTML-инъекция (ссылки,
    подмена форматирования) или падение рассылки из-за незакрытого тега.
    """
    text = "" if value is None else str(value)
    return html.escape(text, quote=False)



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
