import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime

import gspread
from gspread.exceptions import WorksheetNotFound

import config
from app.utils import clean, normalize, now_local, parse_match_datetime

MATCH_HEADERS = [
    "ID",
    "Этап",
    "Регион",
    "Дата",
    "Время",
    "Команда А",
    "Команда Б",
    "Филиал А",
    "Филиал Б",
    "Результат",
    "Напоминание",
]
USER_HEADERS = ["TG ID", "ФИО", "Регион", "Username", "Дата регистрации"]
PRED_HEADERS = ["TG ID", "Матч ID", "Прогноз", "Балл", "Обновлено"]
RESULT_HEADERS = ["№", "ФИО", "Регион", "ТГ", "Баллы"]
DRAW_HEADERS = ["№", "ФИО", "Регион", "ТГ", "Баллы", "Угадано матчей", "Всего матчей", "Угадано %"]

_ID_COL = MATCH_HEADERS.index("ID") + 1
_REMIND_COL = MATCH_HEADERS.index("Напоминание") + 1
_RESULT_COL = MATCH_HEADERS.index("Результат") + 1


@dataclass
class Match:
    row: int
    mid: str
    stage: str = ""
    region: str = ""
    date: str = ""
    time: str = ""
    team_a: str = ""
    team_b: str = ""
    branch_a: str = ""
    branch_b: str = ""
    result: str = ""
    reminded: str = ""

    @property
    def dt(self):
        return parse_match_datetime(self.date, self.time)

    @property
    def finished(self) -> bool:
        return bool(self.result.strip())

    @property
    def winner_side(self):
        value = normalize(self.result)
        if not value:
            return None
        if value in ("а", "a", "1") or value == normalize(self.team_a):
            return "A"
        if value in ("б", "b", "2") or value == normalize(self.team_b):
            return "B"
        return None

    @property
    def resolved(self) -> bool:
        return self.winner_side is not None

    @property
    def winner_team(self) -> str:
        side = self.winner_side
        if side == "A":
            return clean(self.team_a)
        if side == "B":
            return clean(self.team_b)
        return ""

    def side_of(self, prediction: str):
        value = normalize(prediction)
        if not value:
            return None
        if value == normalize(self.team_a):
            return "A"
        if value == normalize(self.team_b):
            return "B"
        return None

    def is_correct(self, prediction: str) -> bool:
        side = self.side_of(prediction)
        return side is not None and side == self.winner_side


@dataclass
class User:
    row: int
    tg_id: int
    fio: str
    region: str
    username: str
    registered_at: str


@dataclass
class Prediction:
    row: int
    tg_id: int
    mid: str
    prediction: str
    score: str = ""
    updated: str = ""


@dataclass
class RatingRow:
    user: User
    points: int = 0
    correct: int = 0
    total: int = 0
    accuracy: float = 0.0
    identity: str = ""
    region: str = ""
    tg: str = ""
    stages: dict = field(default_factory=dict)
    tg_ids: set = field(default_factory=set)


class Sheets:
    """Обёртка над Google Sheets. Данные читаются/пишутся по одному листу."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cache = {}
        self._cache_ttl = 5.0
        self._client = gspread.service_account(filename=config.GOOGLE_CREDENTIALS)
        self._ss = self._client.open_by_key(config.SPREADSHEET_ID)

    # ------------------------------------------------------------------ utils
    def _ws(self, title):
        try:
            return self._ss.worksheet(title)
        except WorksheetNotFound:
            return None

    def _invalidate(self, *titles):
        if not titles:
            self._cache.clear()
            return
        for key in list(self._cache):
            if key[0] in titles:
                del self._cache[key]

    def ensure_worksheet(self, title, headers, cols=None):
        ws = self._ws(title)
        if ws is None:
            ws = self._ss.add_worksheet(
                title=title, rows=1000, cols=cols or (len(headers) + 2)
            )
            ws.update([headers], "A1", value_input_option="RAW")
            self._invalidate()
            return ws
        first = ws.row_values(1)
        if not first:
            ws.update([headers], "A1", value_input_option="RAW")
            self._invalidate(title)
        return ws

    def _rows(self, ws, width):
        key = (ws.title, width)
        now = time.time()
        hit = self._cache.get(key)
        if hit and now - hit[0] < self._cache_ttl:
            return hit[1]
        values = ws.get_all_values()
        data = []
        if values:
            for idx, row in enumerate(values[1:], start=2):
                row = (list(row) + [""] * width)[:width]
                if not any(str(cell).strip() for cell in row):
                    continue
                data.append((idx, row))
        self._cache[key] = (now, data)
        return data

    # ---------------------------------------------------------------- matches
    def get_matches(self):
        ws = self.ensure_worksheet(config.SHEET_MATCHES, MATCH_HEADERS)
        matches = []
        to_fix = []
        for row_idx, row in self._rows(ws, len(MATCH_HEADERS)):
            mid = clean(row[0])
            if not mid:
                mid = uuid.uuid4().hex[:8].upper()
                to_fix.append((row_idx, mid))
            matches.append(
                Match(
                    row=row_idx,
                    mid=mid,
                    stage=clean(row[1]),
                    region=clean(row[2]),
                    date=clean(row[3]),
                    time=clean(row[4]),
                    team_a=clean(row[5]),
                    team_b=clean(row[6]),
                    branch_a=clean(row[7]),
                    branch_b=clean(row[8]),
                    result=clean(row[9]),
                    reminded=clean(row[10]),
                )
            )
        for row_idx, mid in to_fix:
            ws.update_cell(row_idx, _ID_COL, mid)
        if to_fix:
            self._invalidate(config.SHEET_MATCHES)
        return matches

    def get_match(self, mid):
        for match in self.get_matches():
            if match.mid == mid:
                return match
        return None

    def mark_reminded(self, match: Match, stamp: datetime):
        ws = self.ensure_worksheet(config.SHEET_MATCHES, MATCH_HEADERS)
        ws.update_cell(match.row, _REMIND_COL, stamp.strftime("%d.%m.%Y %H:%M"))
        self._invalidate(config.SHEET_MATCHES)

    def create_match(
        self,
        stage,
        date,
        time,
        team_a,
        team_b,
        branch_a="",
        branch_b="",
        region="",
    ):
        """Заводит новый матч (менеджер через бота). Возвращает ID матча."""
        ws = self.ensure_worksheet(config.SHEET_MATCHES, MATCH_HEADERS)
        mid = uuid.uuid4().hex[:8].upper()
        ws.append_row(
            [
                mid,
                clean(stage),
                clean(region),
                clean(date),
                clean(time),
                clean(team_a),
                clean(team_b),
                clean(branch_a),
                clean(branch_b),
                "",
                "",
            ],
            value_input_option="RAW",
        )
        self._invalidate(config.SHEET_MATCHES)
        return mid

    def set_result(self, match: Match, result):
        """Записывает результат матча (имя победившей команды или A/B)."""
        ws = self.ensure_worksheet(config.SHEET_MATCHES, MATCH_HEADERS)
        ws.update_cell(match.row, _RESULT_COL, clean(result))
        self._invalidate(config.SHEET_MATCHES)

    # ------------------------------------------------------------------ users
    def get_user(self, tg_id):
        ws = self.ensure_worksheet(config.SHEET_USERS, USER_HEADERS)
        for row_idx, row in self._rows(ws, len(USER_HEADERS)):
            if clean(row[0]) == str(tg_id):
                return User(
                    row=row_idx,
                    tg_id=tg_id,
                    fio=clean(row[1]),
                    region=clean(row[2]),
                    username=clean(row[3]),
                    registered_at=clean(row[4]),
                )
        return None

    def add_user(self, tg_id, fio, region, username):
        ws = self.ensure_worksheet(config.SHEET_USERS, USER_HEADERS)
        ws.append_row(
            [
                str(tg_id),
                clean(fio),
                clean(region),
                clean(username),
                now_local().strftime("%d.%m.%Y %H:%M"),
            ],
            value_input_option="RAW",
        )
        self._invalidate(config.SHEET_USERS)

    def all_users(self):
        ws = self.ensure_worksheet(config.SHEET_USERS, USER_HEADERS)
        users = []
        for row_idx, row in self._rows(ws, len(USER_HEADERS)):
            tg_raw = clean(row[0])
            if not tg_raw.isdigit():
                continue
            users.append(
                User(
                    row=row_idx,
                    tg_id=int(tg_raw),
                    fio=clean(row[1]),
                    region=clean(row[2]),
                    username=clean(row[3]),
                    registered_at=clean(row[4]),
                )
            )
        return users

    # ------------------------------------------------------------ predictions
    def all_predictions(self):
        ws = self.ensure_worksheet(config.SHEET_PREDICTIONS, PRED_HEADERS)
        preds = []
        for row_idx, row in self._rows(ws, len(PRED_HEADERS)):
            tg_raw = clean(row[0])
            if not tg_raw.isdigit():
                continue
            preds.append(
                Prediction(
                    row=row_idx,
                    tg_id=int(tg_raw),
                    mid=clean(row[1]),
                    prediction=clean(row[2]),
                    score=clean(row[3]),
                    updated=clean(row[4]),
                )
            )
        return preds

    def get_prediction(self, tg_id, mid):
        for pred in self.all_predictions():
            if pred.tg_id == tg_id and pred.mid == mid:
                return pred
        return None

    def set_prediction(self, tg_id, mid, prediction):
        ws = self.ensure_worksheet(config.SHEET_PREDICTIONS, PRED_HEADERS)
        stamp = now_local().strftime("%d.%m.%Y %H:%M")
        with self._lock:
            for row_idx, row in self._rows(ws, len(PRED_HEADERS)):
                if clean(row[0]) == str(tg_id) and clean(row[1]) == mid:
                    ws.update(
                        [[prediction, "", stamp]],
                        f"C{row_idx}:E{row_idx}",
                        value_input_option="RAW",
                    )
                    self._invalidate(config.SHEET_PREDICTIONS)
                    return
            ws.append_row(
                [str(tg_id), mid, prediction, "", stamp],
                value_input_option="RAW",
            )
            self._invalidate(config.SHEET_PREDICTIONS)

    def write_scores(self, scores):
        """scores: dict[(tg_id, mid)] -> int. Обновляет столбец 'Балл'."""
        ws = self.ensure_worksheet(config.SHEET_PREDICTIONS, PRED_HEADERS)
        updates = []
        for row_idx, row in self._rows(ws, len(PRED_HEADERS)):
            tg_raw = clean(row[0])
            if not tg_raw.isdigit():
                continue
            key = (int(tg_raw), clean(row[1]))
            if key not in scores:
                continue
            new_value = str(scores[key])
            if clean(row[3]) != new_value:
                updates.append(
                    {
                        "range": f"D{row_idx}",
                        "values": [[new_value]],
                    }
                )
        if updates:
            ws.batch_update(updates, value_input_option="RAW")
            self._invalidate(config.SHEET_PREDICTIONS)

    # ---------------------------------------------------------------- results
    def write_results(self, rows, headers=None):
        headers = headers or RESULT_HEADERS
        ws = self.ensure_worksheet(config.SHEET_RESULTS, headers)
        ws.clear()
        ws.update([headers] + rows, "A1", value_input_option="RAW")

    def write_draw(self, rows):
        ws = self.ensure_worksheet(config.SHEET_DRAW, DRAW_HEADERS)
        ws.clear()
        ws.update([DRAW_HEADERS] + rows, "A1", value_input_option="RAW")

    def write_scoreboard(self, headers, rows, title=None):
        """Пишет матрицу баллов «участники × матчи» (1/0/·) + сумма.

        title — имя листа: общий итог «Баллы» либо название этапа.
        """
        sheet = title or config.SHEET_SCORES
        ws = self.ensure_worksheet(sheet, headers, cols=60)
        need_cols = len(headers)
        need_rows = len(rows) + 1
        if ws.col_count < need_cols or ws.row_count < need_rows:
            ws.resize(
                rows=max(ws.row_count, need_rows),
                cols=max(ws.col_count, need_cols),
            )
        ws.clear()
        ws.update([headers] + rows, "A1", value_input_option="RAW")

    def add_match_rows(self, rows):
        ws = self.ensure_worksheet(config.SHEET_MATCHES, MATCH_HEADERS)
        if rows:
            ws.append_rows(rows, value_input_option="RAW")
            self._invalidate(config.SHEET_MATCHES)


sheets = Sheets()
