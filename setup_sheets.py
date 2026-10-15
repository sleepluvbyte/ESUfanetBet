"""Создаёт нужные листы в Google Sheets и переносит данные из старого листа.

Запуск:  python setup_sheets.py
"""

import uuid
from datetime import datetime

import config
from app.sheets import MATCH_HEADERS, PRED_HEADERS, USER_HEADERS, sheets


def migrate_old_matches():
    ws_matches = sheets.ensure_worksheet(config.SHEET_MATCHES, MATCH_HEADERS)
    existing = ws_matches.get_all_values()
    if len(existing) > 1:
        print("Лист «Матчи» уже заполнен — миграция не нужна.")
        return

    try:
        old = None
        for title in ("Матч", "Матч 0", "Матчи 0"):
            try:
                old = sheets._ss.worksheet(title)
                break
            except Exception:
                continue
    except Exception:
        old = None

    rows = []
    if old is not None:
        for row in old.get_all_values()[1:]:
            if not any(str(cell).strip() for cell in row):
                continue
            row = (list(row) + [""] * 6)[:6]
            date, time_, team_a, team_b, branch_a, branch_b = row
            rows.append(
                [
                    uuid.uuid4().hex[:8].upper(),
                    "Отборочный",
                    branch_a or branch_b,
                    date,
                    time_,
                    team_a,
                    team_b,
                    branch_a,
                    branch_b,
                    "",
                    "",
                ]
            )

    rows.extend(
        [
            [
                uuid.uuid4().hex[:8].upper(),
                "Полуфинал",
                "Москва",
                "20/10/2026",
                "18:00",
                "Team Spirit",
                "Team Timofey Palaev",
                "Москва",
                "Стерлитамак",
                "",
                "",
            ],
            [
                uuid.uuid4().hex[:8].upper(),
                "Финал онлайн",
                "Онлайн",
                "25/10/2026",
                "19:00",
                "Победитель П1",
                "Победитель П2",
                "",
                "",
                "",
                "",
            ],
            [
                uuid.uuid4().hex[:8].upper(),
                "Финал оффлайн",
                "Оффлайн",
                "01/11/2026",
                "15:00",
                "Победитель Ф1",
                "Победитель Ф2",
                "",
                "",
                "",
                "",
            ],
        ]
    )

    if rows:
        ws_matches.update(rows, f"A2", value_input_option="RAW")
        print(f"Добавлено матчей: {len(rows)}")
    else:
        print("Нет данных для переноса.")


def main():
    sheets.ensure_worksheet(config.SHEET_MATCHES, MATCH_HEADERS)
    sheets.ensure_worksheet(config.SHEET_USERS, USER_HEADERS)
    sheets.ensure_worksheet(config.SHEET_PREDICTIONS, PRED_HEADERS)
    sheets.ensure_worksheet(
        config.SHEET_SCORES, ["№", "ФИО", "Регион", "ТГ", "Сумма"], cols=60
    )
    for stage in config.STAGES:
        sheets.ensure_worksheet(
            stage, ["№", "ФИО", "Регион", "ТГ", "Сумма"], cols=60
        )
    print("Листы созданы/проверены:")
    print(" -", config.SHEET_MATCHES)
    print(" -", config.SHEET_USERS)
    print(" -", config.SHEET_PREDICTIONS)
    print(" -", config.SHEET_SCORES, "(общая матрица баллов)")
    print(" -", ", ".join(config.STAGES), "(матрица баллов по этапам)")
    print(" -", config.SHEET_RESULTS, "(заполняется командой /export)")

    migrate_old_matches()
    print("Готово.")


if __name__ == "__main__":
    main()
