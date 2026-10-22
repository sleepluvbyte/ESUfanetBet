import asyncio
from datetime import timedelta

from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

import config
from app.scoring import compute_rating, schedule_scoreboard_refresh
from app.sheets import sheets
from app.utils import esc, format_dt, now_local


def _reminder_text(match) -> str:
    moment = format_dt(match.dt) if match.dt else f"{match.date} {match.time}"
    minutes = config.REMINDER_MINUTES
    if minutes % 60 == 0:
        when = f"{minutes // 60} ч."
    else:
        when = f"{minutes} мин."
    lines = [
        f"⏰ <b>Матч начнётся через {when}</b>\n",
        f"<b>{esc(match.team_a)}</b> — <b>{esc(match.team_b)}</b>",
        f"🕒 {esc(moment)}",
    ]
    if match.stage:
        lines.append(f"🏷 Этап: {esc(match.stage)}")
    if match.region:
        lines.append(f"📍 Регион: {esc(match.region)}")
    lines.append("\nНе забудь сделать прогноз! 🔮")
    return "\n".join(lines)


def _match_button(mid):
    kb = InlineKeyboardBuilder()
    kb.button(text="🔮 Сделать прогноз", callback_data=f"match:{mid}")
    return kb.as_markup()


async def _send_all(bot: Bot, users, text, markup=None):
    for user in users:
        try:
            await bot.send_message(user.tg_id, text, reply_markup=markup)
        except Exception:
            pass
        await asyncio.sleep(0.05)


async def reminder_job(bot: Bot):
    matches = sheets.get_matches()
    if not matches:
        return
    now = now_local()
    limit = now + timedelta(minutes=config.REMINDER_MINUTES)
    users = sheets.all_users()
    if not users:
        return
    for match in matches:
        if match.resolved or match.reminded:
            continue
        moment = match.dt
        if moment is None:
            continue
        if now < moment <= limit:
            await _send_all(
                bot, users, _reminder_text(match), _match_button(match.mid)
            )
            sheets.mark_reminded(match, now)


async def sync_scores_job(bot: Bot):
    _, score_map, _ = compute_rating()
    if score_map:
        sheets.write_scores(score_map)
    # «Баллы» — живой снимок: подхватываем и ручные правки матча в таблице.
    schedule_scoreboard_refresh()


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)
    scheduler.add_job(
        reminder_job,
        IntervalTrigger(minutes=1),
        args=[bot],
        id="reminders",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        sync_scores_job,
        IntervalTrigger(minutes=5),
        args=[bot],
        id="sync_scores",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    return scheduler
