import asyncio
import logging
from collections import defaultdict

import config
from app.sheets import RatingRow, sheets
from app.utils import DT_MAX, normalize

log = logging.getLogger("bot.scoreboard")

RESULT_HEADERS_EXTRA = [
    "Угадано %",
    "Угадано матчей",
    "Всего матчей",
    "Отборочный",
    "Полуфинал",
    "Финал онлайн",
    "Финал оффлайн",
    "В розыгрыше (70%+)",
]


def _identity(user) -> str:
    """Ключ участника: нормализованное ФИО (чтобы не было дублей), иначе TG ID."""
    return normalize(user.fio) or f"tg:{user.tg_id}"


def _tg_display(user) -> str:
    username = user.username.lstrip("@").strip()
    return f"@{username}" if username else str(user.tg_id)


def _resolved(matches):
    return [match for match in matches if match.resolved]


def _prediction_score_map(matches, predictions):
    """Карта (tg_id, mid) -> 0/1 для записи в лист «Прогнозы»."""
    resolved = {match.mid: match for match in _resolved(matches)}
    result = {}
    for pred in predictions:
        match = resolved.get(pred.mid)
        if match is None:
            continue
        result[(pred.tg_id, pred.mid)] = 1 if match.is_correct(pred.prediction) else 0
    return result


def grouped_rating(users, matches, predictions, stage=None):
    """Рейтинг, где дубликаты ФИО объединены в одного участника.

    Матч учитывается один раз на участника даже при нескольких аккаунтах.
    """
    resolved = _resolved(matches)
    if stage:
        resolved = [m for m in resolved if normalize(m.stage) == normalize(stage)]
    total = len(resolved)

    ident_of = {user.tg_id: _identity(user) for user in users}
    groups = {}
    order = []
    for user in users:
        key = _identity(user)
        group = groups.get(key)
        if group is None:
            group = {
                "fio": user.fio,
                "region": user.region,
                "tg": _tg_display(user),
                "tg_ids": set(),
                "points": 0,
                "correct": 0,
                "stages": {s: 0 for s in config.STAGES},
                "registered_at": user.registered_at,
                "rep": user,
            }
            groups[key] = group
            order.append(key)
        elif not group["region"] and user.region:
            group["region"] = user.region
        group["tg_ids"].add(user.tg_id)

    preds_by_match = defaultdict(list)
    for pred in predictions:
        preds_by_match[pred.mid].append(pred)

    for match in resolved:
        winners = set()
        for pred in preds_by_match.get(match.mid, []):
            key = ident_of.get(pred.tg_id)
            if key is None:
                continue
            if match.is_correct(pred.prediction):
                winners.add(key)
        for key in winners:
            groups[key]["correct"] += 1
            groups[key]["points"] += 1
            if match.stage in groups[key]["stages"]:
                groups[key]["stages"][match.stage] += 1

    rows = []
    for key in order:
        group = groups[key]
        won = group["correct"]
        rows.append(
            RatingRow(
                user=group["rep"],
                points=group["points"],
                correct=won,
                total=total,
                accuracy=(won / total) if total else 0.0,
                identity=key,
                region=group["region"],
                tg=group["tg"],
                stages=group["stages"],
                tg_ids=group["tg_ids"],
            )
        )
    rows.sort(key=lambda r: (-r.points, -r.correct, r.user.registered_at, r.user.fio.lower()))
    return rows, total


def compute_rating(stage=None, users=None, matches=None, predictions=None):
    users = users if users is not None else sheets.all_users()
    matches = matches if matches is not None else sheets.get_matches()
    predictions = predictions if predictions is not None else sheets.all_predictions()
    rows, total = grouped_rating(users, matches, predictions, stage=stage)
    score_map = _prediction_score_map(matches, predictions)
    return rows, score_map, total


def build_full_export():
    users = sheets.all_users()
    matches = sheets.get_matches()
    predictions = sheets.all_predictions()
    rating, score_map, total = compute_rating(
        users=users, matches=matches, predictions=predictions
    )
    rows = []
    draw_rows = []
    for idx, row in enumerate(rating, start=1):
        eligible = (
            row.total > 0 and row.accuracy >= config.DRAW_THRESHOLD
        )
        record = [
            str(idx),
            row.user.fio,
            row.region,
            row.tg,
            str(row.points),
            f"{row.accuracy * 100:.0f}%",
            str(row.correct),
            str(row.total),
        ]
        record += [str(row.stages.get(stage, 0)) for stage in config.STAGES]
        record.append("да" if eligible else "нет")
        rows.append(record)
        if eligible:
            draw_rows.append(
                [
                    str(len(draw_rows) + 1),
                    row.user.fio,
                    row.region,
                    row.tg,
                    str(row.points),
                    str(row.correct),
                    str(row.total),
                    f"{row.accuracy * 100:.0f}%",
                ]
            )
    headers = ["№", "ФИО", "Регион", "ТГ", "Баллы"] + RESULT_HEADERS_EXTRA
    return headers, rows, score_map, rating, draw_rows


def export_results():
    """Выгружает лист «Итоги» (все участники, ФИО без дублей) и «Розыгрыш»
    (нумерованный список тех, кто угадал порог — для ручного розыгрыша)."""
    headers, rows, score_map, rating, draw_rows = build_full_export()
    sheets.write_results(rows, headers=headers)
    sheets.write_draw(draw_rows)
    return len(rows), len(draw_rows)


def build_scoreboard(stage=None):
    """Матрица «Баллы» по одному этапу (или целиком, если stage=None)."""
    users, matches, predictions = _scoreboard_snapshot()
    return _scoreboard_rows(users, matches, predictions, stage)


def _scoreboard_snapshot():
    """Одно чтение таблицы на все листы-матрицы (экономим квоту Google)."""
    return sheets.all_users(), sheets.get_matches(), sheets.all_predictions()


def _scoreboard_rows(users, matches, predictions, stage=None):
    """Матрица «участники × матчи»: 1/0/· + сумма баллов.

    Строки — участники (ФИО без дублей), столбцы — матчи.
    В ячейке: 1 — прогноз верный, 0 — прогноз был, но неверный,
    «·» — прогноз сделан, матч ещё не сыгран, пусто — прогноза нет.
    stage=None — все матчи; иначе — только матчи указанного этапа.
    """
    rating, _ = grouped_rating(users, matches, predictions, stage=stage)

    if stage:
        wanted = normalize(stage)
        matches = [m for m in matches if normalize(m.stage) == wanted]
    ordered = sorted(matches, key=lambda m: m.dt or DT_MAX)
    ident_of = {user.tg_id: _identity(user) for user in users}

    preds_by_match = defaultdict(list)
    for pred in predictions:
        preds_by_match[pred.mid].append(pred)

    headers = ["№", "ФИО", "Регион", "ТГ"]
    headers += [f"{m.team_a}—{m.team_b}" for m in ordered]
    headers.append("Сумма")

    rows = []
    for idx, row in enumerate(rating, start=1):
        cells = [str(idx), row.user.fio, row.region, row.tg]
        for match in ordered:
            mark = ""
            for pred in preds_by_match.get(match.mid, []):
                if ident_of.get(pred.tg_id) != row.identity:
                    continue
                if match.resolved:
                    if match.is_correct(pred.prediction):
                        mark = "1"
                        break
                    mark = mark or "0"
                elif mark == "":
                    mark = "·"
            cells.append(mark)
        cells.append(str(row.points))
        rows.append(cells)
    return headers, rows


def scoreboard_titles():
    """(фильтр этапа, имя листа): общий итог + по одному листу на каждый этап."""
    titles = [(None, config.SHEET_SCORES)]
    titles += [(stage, stage) for stage in config.STAGES]
    return titles


def refresh_scoreboard():
    """Перезаписывает «Баллы» целиком: общий лист + лист каждого этапа.

    Данные читаются один раз на все листы — иначе упираемся в квоту Google.
    """
    users, matches, predictions = _scoreboard_snapshot()
    count = 0
    for stage, title in scoreboard_titles():
        headers, rows = _scoreboard_rows(users, matches, predictions, stage)
        sheets.write_scoreboard(headers, rows, title=title)
        count = len(rows)
    return count


def _safe_refresh():
    try:
        refresh_scoreboard()
    except Exception as exc:
        log.warning("Лист «Баллы» не обновился: %s", exc)


async def refresh_scoreboard_bg():
    """Обновляет матрицу «Баллы» в фоне, чтобы не тормозить хендлер."""
    try:
        await asyncio.to_thread(_safe_refresh)
    except Exception as exc:
        log.warning("Лист «Баллы» не обновился: %s", exc)


def schedule_scoreboard_refresh():
    """Ставит пересчёт «Баллы» в фон.

    Вызывать после любого изменения: сохранение прогноза, ввод результата.
    Если event loop не запущен (скрипты) — делает сразу.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        _safe_refresh()
        return None
    return asyncio.create_task(refresh_scoreboard_bg())
