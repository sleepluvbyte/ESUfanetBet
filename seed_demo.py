"""Наполняет таблицу тестовыми данными для проверки всех этапов.

Запуск:  python seed_demo.py
Очистить: python clear_demo.py

Создаёт демо-участников (tg_id 9000000xx, регион «ДЕМО»), 5 сыгранных
отборочных матчей, финальные этапы и матч через 90 минут (для проверки
напоминания). Плюс прогнозы, включая дубль ФИО для проверки дедупа.
"""

from datetime import datetime, timedelta

from app.sheets import sheets
from app.utils import now_local

DEMO_REGION = "ДЕМО"
DEMO_TG_MIN = 900000000
# Диапазон демо-аккаунтов. Важно: проверять ИМЕННО диапазон, а не ">= MIN" —
# иначе под правило попадают реальные 10-значные ID (например, 1227190624).
DEMO_TG_MAX = 900000999


def _is_demo_tg(cell) -> bool:
    """True только для демо-аккаунтов 900000000..900000999."""
    if not cell or not cell.isdigit():
        return False
    value = int(cell)
    return DEMO_TG_MIN <= value <= DEMO_TG_MAX

DEMO_USERS = [
    (900000001, "Демо Алексеев Алексей", "Уфа", "demo_alex"),
    (900000002, "Демо Борисов Борис", "Омск", "demo_boris"),
    (900000003, "Демо Алексеев Алексей", "Уфа", "demo_alex_dupe"),
    (900000004, "Демо Волкова Вера", "Смоленск", "demo_vera"),
]

# (Команда А, Команда Б, Победитель)
QUAL = [
    ("Team Spirit", "Team Timofey", "Team Spirit"),
    ("NAVI", "FaZe", "NAVI"),
    ("Virtus.pro", "G2", "G2"),
    ("Astralis", "NAVI", "NAVI"),
    ("Team Spirit", "Virtus.pro", "Team Spirit"),
]

# Прогнозы демо-участников: список True/False по матчам QUAL
DEMO_PREDS = {
    900000001: [True, True, True, True, True],
    900000003: [True, False, False, False, False],
    900000002: [True, True, True, True, False],
    900000004: [True, True, False],
}


def _dt(days, hour, minute):
    moment = now_local() + timedelta(days=days)
    return moment.strftime("%d/%m/%Y"), f"{hour:02d}:{minute:02d}"


def _loser(team_a, team_b, winner):
    return team_b if winner == team_a else team_a


def clear_demo():
    users_ws = sheets._ws("Участники")
    if users_ws:
        rows = users_ws.get_all_values()
        for idx in range(len(rows), 1, -1):
            cell = rows[idx - 1][0].strip() if rows[idx - 1] else ""
            if _is_demo_tg(cell):
                users_ws.delete_rows(idx)

    pred_ws = sheets._ws("Прогнозы")
    if pred_ws:
        rows = pred_ws.get_all_values()
        for idx in range(len(rows), 1, -1):
            cell = rows[idx - 1][0].strip() if rows[idx - 1] else ""
            if _is_demo_tg(cell):
                pred_ws.delete_rows(idx)

    match_ws = sheets._ws("Матчи")
    if match_ws:
        rows = match_ws.get_all_values()
        for idx in range(len(rows), 1, -1):
            row = rows[idx - 1]
            region = row[2].strip() if len(row) > 2 else ""
            if region == DEMO_REGION:
                match_ws.delete_rows(idx)


def main():
    print("Чищу старые демо-данные...")
    clear_demo()

    print("Добавляю демо-участников...")
    for tg_id, fio, region, username in DEMO_USERS:
        sheets.add_user(tg_id, fio, region, username)

    print("Добавляю демо-матчи...")
    match_rows = []
    qual_ids = []
    for i, (team_a, team_b, winner) in enumerate(QUAL, start=1):
        mid = f"DEMO{i:02d}"
        qual_ids.append(mid)
        date, time_ = _dt(-2, 18, 0)
        match_rows.append(
            [
                mid,
                "Отборочный",
                DEMO_REGION,
                date,
                time_,
                team_a,
                team_b,
                "Москва",
                "Омск",
                winner,
                "",
            ]
        )

    for i, (stage, days) in enumerate(
        [("Полуфинал", 1), ("Финал онлайн", 3), ("Финал оффлайн", 7)], start=6
    ):
        mid = f"DEMO{i:02d}"
        date, time_ = _dt(days, 19, 0)
        match_rows.append(
            [
                mid,
                stage,
                DEMO_REGION,
                date,
                time_,
                "Team Spirit",
                "NAVI",
                "Москва",
                "Омск",
                "",
                "",
            ]
        )

    now = now_local() + timedelta(minutes=90)
    match_rows.append(
        [
            "DEMO09",
            "Отборочный",
            DEMO_REGION,
            now.strftime("%d/%m/%Y"),
            now.strftime("%H:%M"),
            "FaZe",
            "Astralis",
            "Москва",
            "Смоленск",
            "",
            "",
        ]
    )
    sheets.add_match_rows(match_rows)

    print("Добавляю демо-прогнозы...")
    for tg_id, results in DEMO_PREDS.items():
        for match_index, is_correct in enumerate(results):
            team_a, team_b, winner = QUAL[match_index]
            team = winner if is_correct else _loser(team_a, team_b, winner)
            sheets.set_prediction(tg_id, qual_ids[match_index], team)

    print("\nГотово! Демо-данные добавлены.")
    print("Проверка:")
    print(" - бот: /id, /start (зарегистрируйся как реальный) ")
    print(" - в боте: /rating, /matches")
    print(" - админ: /test, /dryrun, /refresh, /export")
    print(" - лист «Матчи»: DEMO09 начнётся ~через 90 мин (сработает напоминание)")
    print("\nОчистить: python clear_demo.py")


if __name__ == "__main__":
    main()
