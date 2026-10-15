"""Удаляет тестовые данные, созданные seed_demo.py.

Запуск:  python clear_demo.py
Удаляет: демо-участников (tg_id 9000000xx), их прогнозы, матчи с регионом «ДЕМО».
Также очищает листы «Итоги» и «Розыгрыш».
"""

import config
from seed_demo import clear_demo
from app.sheets import sheets


def main():
    clear_demo()
    for name in (config.SHEET_RESULTS, config.SHEET_DRAW):
        ws = sheets._ws(name)
        if ws:
            ws.clear()
    print("Демо-данные удалены. Листы «Итоги» и «Розыгрыш» очищены.")


if __name__ == "__main__":
    main()
