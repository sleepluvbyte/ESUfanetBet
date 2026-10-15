import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

import config
from app.handlers import admin, menu, registration

log = logging.getLogger("bot.error")

session = AiohttpSession(proxy=config.PROXY_URL or None)

bot = Bot(
    token=config.BOT_TOKEN,
    session=session,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher(storage=MemoryStorage())


@dp.error()
async def on_handler_error(event: ErrorEvent):
    """Любая ошибка в хендлере: пишем в лог и снимаем «вечный спиннер» с кнопки."""
    log.error("Ошибка обработки update: %s", event.exception, exc_info=event.exception)
    callback = event.update.callback_query
    if callback is not None:
        try:
            await callback.answer(
                "⚠️ Не получилось сохранить. Попробуй ещё раз — детали в логах сервера.",
                show_alert=True,
            )
        except Exception:
            pass
    return True

dp.include_router(registration.router)
dp.include_router(menu.router)
dp.include_router(admin.router)
