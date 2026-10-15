import asyncio
import logging

from aiogram.exceptions import TelegramNetworkError
from aiogram.types import BotCommand, BotCommandScopeChat

import config
from app.bot import bot, dp
from app.scheduler import setup_scheduler
from app.sheets import MATCH_HEADERS, PRED_HEADERS, USER_HEADERS, sheets

COMMANDS = [
    BotCommand(command="start", description="Меню и регистрация"),
    BotCommand(command="matches", description="Ближайшие матчи"),
    BotCommand(command="rating", description="Рейтинг участников"),
    BotCommand(command="me", description="Мой профиль и баллы"),
    BotCommand(command="id", description="Мой Telegram ID"),
    BotCommand(command="help", description="Помощь"),
]

ADMIN_COMMANDS = COMMANDS + [
    BotCommand(command="admin", description="🛠 Админ-панель"),
    BotCommand(command="addmatch", description="➕ Новый матч"),
    BotCommand(command="result", description="✅ Результат матча"),
    BotCommand(command="scoreboard", description="🧮 Обновить «Баллы»"),
]


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("bot")

    log.info("Проверяю листы Google Sheets...")
    sheets.ensure_worksheet(config.SHEET_MATCHES, MATCH_HEADERS)
    sheets.ensure_worksheet(config.SHEET_USERS, USER_HEADERS)
    sheets.ensure_worksheet(config.SHEET_PREDICTIONS, PRED_HEADERS)
    score_headers = ["№", "ФИО", "Регион", "ТГ", "Сумма"]
    sheets.ensure_worksheet(config.SHEET_SCORES, score_headers, cols=60)
    for stage in config.STAGES:
        sheets.ensure_worksheet(stage, score_headers, cols=60)

    scheduler = setup_scheduler(bot)
    log.info("Планировщик запущен (напоминания, дневной рейтинг).")

    try:
        await bot.set_my_commands(COMMANDS)
        for admin_id in config.ADMIN_IDS:
            try:
                await bot.set_my_commands(
                    ADMIN_COMMANDS,
                    scope=BotCommandScopeChat(chat_id=admin_id),
                )
            except Exception as exc:
                log.warning("Не смог задать админ-команды для %s: %s", admin_id, exc)
        await bot.delete_webhook(drop_pending_updates=True)
    except TelegramNetworkError as exc:
        log.error("=" * 60)
        log.error("Нет соединения с api.telegram.org: %s", exc)
        log.error("Скорее всего Telegram заблокирован вашей сетью/провайдером.")
        log.error("Варианты решения:")
        log.error("  1) Прописать прокси в .env: PROXY_URL=socks5://user:pass@host:1080")
        log.error("     (для socks5 нужен пакет: pip install aiohttp-socks)")
        log.error("  2) Запустить через VPN.");
        log.error("  3) Запустить бота на сервере/VPS с доступом к Telegram.");
        log.error("Проверить доступ: python check_net.py");
        log.error("=" * 60)
        scheduler.shutdown(wait=False)
        await bot.session.close()
        return

    log.info("Бот запущен. Нажми Ctrl+C для остановки.")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
