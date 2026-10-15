import asyncio
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import config
from app.scoring import compute_rating, schedule_scoreboard_refresh
from app.sheets import sheets
from app.utils import format_dt, now_local


def _reminder_text(match) -> str:
    moment = format_dt(match.dt) if match.dt else f"{match.date} {match.time}"
    minutes = config.REMINDER_MINUTES
    if minutes % 60 == 0:
        when = f"{minutes // 60} ч."
    else:
        when = f"{minutes} мин."
    lines = [
        f"⏰ <b>Матч начнётся через {when}</b>\n",
        f"<b>{match.team_a}</b> — <b>{match.team_b}</b>",
        f"🕒 {moment}",
    ]
    if match.stage:
        lines.append(f"🏷 Этап: {match.stage}")
    if match.region:
        lines.append(f"📍 Регион: {match.region}")
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


async def daily_rating_job(bot: Bot):
    rating, _, total = compute_rating()
    if not rating:
        return

    schedule_scoreboard_refresh()

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    top_lines = [f"🏆 <b>Итоги дня</b> (матчей сыграно: {total})\n"]
    for place, row in enumerate(rating[:10], start=1):
        top_lines.append(
            f"{medals.get(place, f'{place}.')} {row.user.fio} — {row.points} б"
        )
    top_text = "\n".join(top_lines)

    if config.RATING_CHAT_ID:
        try:
            await bot.send_message(int(config.RATING_CHAT_ID), top_text)
        except Exception:
            pass
        return

    for place, row in enumerate(rating, start=1):
        try:
            await bot.send_message(
                row.user.tg_id,
                f"🏆 <b>Итоги дня</b>\nТвоё место: <b>{place}</b> из {len(rating)}\n"
                f"Баллов: <b>{row.points}</b> (угадано {row.correct}/{row.total})\n\n"
                + top_text,
            )
        except Exception:
            pass
        await asyncio.sleep(0.05)


def _rating_time():
    try:
        hour, minute = config.RATING_TIME.split(":")
        return int(hour), int(minute)
    except Exception:
        return 21, 0


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
    hour, minute = _rating_time()
    scheduler.add_job(
        daily_rating_job,
        CronTrigger(hour=hour, minute=minute),
        args=[bot],
        id="daily_rating",
        max_instances=1,
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
