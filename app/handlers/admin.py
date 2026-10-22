import asyncio

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from app import keyboards as kb
from app.scoring import (
    build_full_export,
    compute_rating,
    export_results,
    refresh_scoreboard,
    schedule_scoreboard_refresh,
)
from app.sheets import sheets
from app.states import AdminStates
from app.utils import DT_MAX, clean, esc, now_local, parse_match_datetime, sanitize

router = Router()


def _is_admin(tg_id) -> bool:
    return tg_id in config.ADMIN_IDS


async def _denied(message: Message):
    if not config.ADMIN_IDS:
        await message.answer(
            "Админы не настроены. Укажите ADMIN_IDS в файле .env"
        )
    else:
        await message.answer("Команда только для админов.")


ADMIN_HELP = (
    "🛠 <b>Админ-панель</b>\n\n"
    "➕ <b>Новый матч</b> — завести матч (/addmatch). Матч попадёт в таблицу,\n"
    "   а всем участникам уйдёт анонс с кнопкой «Сделать прогноз».\n"
    "✅ <b>Результат</b> — отметить победителя (/result), баллы пересчитаются.\n"
    "🧮 <b>Баллы</b> — матрицу «участники × матчи» (/scoreboard):\n"
    "   лист «Баллы» целиком + отдельный лист на каждый этап.\n\n"
    "Прочее:\n"
    "/stats — статистика турнира\n"
    "/test — проверка настроек перед турниром\n"
    "/dryrun — превью напоминания (только тебе)\n"
    "/refresh — пересчитать баллы прогнозов\n"
    "/export — выгрузить «Итоги» и «Розыгрыш»\n"
    "/broadcast — рассылка всем участникам\n"
    "/cancel — отменить текущее действие"
)


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not _is_admin(message.from_user.id):
        await _denied(message)
        return
    await message.answer(ADMIN_HELP, reply_markup=kb.admin_menu_kb())


@router.callback_query(F.data == "adm:add")
async def cb_adm_add(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        await call.answer("Только для админов", show_alert=True)
        return
    await _start_add_match(call.message, state)
    await call.answer()


def _stats_text() -> str:
    users = sheets.all_users()
    matches = sheets.get_matches()
    preds = sheets.all_predictions()
    finished = [m for m in matches if m.resolved]
    return (
        f"📊 <b>Статистика</b>\n\n"
        f"Участников: <b>{len(users)}</b>\n"
        f"Матчей всего: <b>{len(matches)}</b>\n"
        f"Матчей с результатом: <b>{len(finished)}</b>\n"
        f"Прогнозов: <b>{len(preds)}</b>"
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not _is_admin(message.from_user.id):
        await _denied(message)
        return
    await message.answer(_stats_text())


@router.message(Command("refresh"))
async def cmd_refresh(message: Message):
    if not _is_admin(message.from_user.id):
        await _denied(message)
        return
    _, _, score_map, rating, _ = build_full_export()
    sheets.write_scores(score_map)
    await message.answer(
        f"✅ Пересчитал баллы: {len(score_map)} прогнозов, {len(rating)} участников."
    )


@router.message(Command("export"))
async def cmd_export(message: Message):
    if not _is_admin(message.from_user.id):
        await _denied(message)
        return
    await message.answer("⏳ Формирую итоговую таблицу...")
    participants, eligible = export_results()
    schedule_scoreboard_refresh()
    await message.answer(
        f"✅ Готово!\n"
        f"Лист «{config.SHEET_RESULTS}»: {participants} участников (ФИО без дублей) — "
        f"статистика по этапам и флаг «В розыгрыше».\n"
        f"Лист «{config.SHEET_DRAW}»: {eligible} человек с порогом "
        f"{int(config.DRAW_THRESHOLD * 100)}%+ и готовыми порядковыми номерами "
        f"для розыгрыша.\n"
        f"Лист «{config.SHEET_SCORES}» + лист каждого этапа — матрица "
        f"«участники × матчи» с баллами."
    )


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await _denied(message)
        return
    await state.set_state(AdminStates.broadcast)
    await message.answer(
        "Введи текст рассылки (поддерживается HTML) или /cancel для отмены."
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.")


@router.message(AdminStates.broadcast)
async def do_broadcast(message: Message, state: FSMContext):
    await state.clear()
    text = message.html_text if message.text else ""
    if not text:
        await message.answer("Пустое сообщение, отмена.")
        return

    from app.bot import bot

    users = sheets.all_users()
    sent = 0
    failed = 0
    for user in users:
        try:
            await bot.send_message(user.tg_id, text)
            sent += 1
        except Exception:
            failed += 1
    await message.answer(f"📨 Отправлено: {sent}, ошибок: {failed}.")


@router.message(Command("test"))
async def cmd_test(message: Message):
    if not _is_admin(message.from_user.id):
        await _denied(message)
        return
    users = sheets.all_users()
    matches = sheets.get_matches()
    preds = sheets.all_predictions()
    finished = [m for m in matches if m.resolved]
    now = now_local()
    upcoming = sorted(
        (m for m in matches if not m.resolved and m.dt and m.dt > now),
        key=lambda m: m.dt,
    )
    admins = ", ".join(map(str, sorted(config.ADMIN_IDS))) or "не заданы ❌"
    lines = [
        "🧪 <b>Проверка настроек</b>\n",
        f"Токен: {'✅' if config.BOT_TOKEN else '❌'}",
        f"Таблица: <code>{config.SPREADSHEET_ID}</code>",
        f"Админы: <code>{admins}</code>",
        f"Филиалы: {len(config.BRANCHES)}",
        f"Напоминание за: {config.REMINDER_MINUTES} мин",
        f"Порог розыгрыша: {config.DRAW_THRESHOLD:.0%}\n",
        f"Участников: <b>{len(users)}</b>",
        f"Матчей: <b>{len(matches)}</b> (сыграно {len(finished)})",
        f"Прогнозов: <b>{len(preds)}</b>",
    ]
    if upcoming:
        match = upcoming[0]
        mins = int((match.dt - now).total_seconds() // 60)
        fire = "сработает ✅" if mins <= config.REMINDER_MINUTES else "пока не в окне"
        lines.append(
            f"\nБлижайший матч: {esc(match.team_a)} — {esc(match.team_b)}\n"
            f"через {mins} мин · напоминание {fire}"
        )
    else:
        lines.append("\nПредстоящих матчей нет.")
    await message.answer("\n".join(lines))


@router.message(Command("dryrun"))
async def cmd_dryrun(message: Message):
    if not _is_admin(message.from_user.id):
        await _denied(message)
        return
    from app.scheduler import _match_button, _reminder_text

    now = now_local()
    upcoming = sorted(
        (m for m in sheets.get_matches() if not m.resolved and m.dt and m.dt > now),
        key=lambda m: m.dt,
    )
    if not upcoming:
        await message.answer("Нет предстоящих матчей для превью.")
        return
    match = upcoming[0]
    await message.answer(
        f"Превью напоминания (только тебе): {esc(match.team_a)} — {esc(match.team_b)}"
    )
    await message.answer(
        _reminder_text(match), reply_markup=_match_button(match.mid)
    )


# ======================================================= создание матча (FSM)
async def _start_add_match(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(AdminStates.match_stage)
    await message.answer(
        "➕ <b>Новый матч</b>\n\nШаг 1/7. Выбери этап (вид матча):",
        reply_markup=kb.stages_kb(),
    )


@router.message(Command("addmatch"))
async def cmd_addmatch(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await _denied(message)
        return
    await _start_add_match(message, state)


@router.callback_query(F.data.in_({"mcancel", "rclose"}))
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_text("Отменено.")
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data.startswith("mstage:"))
async def cb_mstage(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        await call.answer("Только для админов", show_alert=True)
        return
    try:
        stage = config.STAGES[int(call.data.split(":", 1)[1])]
    except (IndexError, ValueError):
        await call.answer("Ошибка этапа", show_alert=True)
        return
    await state.update_data(stage=stage)
    await state.set_state(AdminStates.match_date)
    await call.message.edit_text(
        f"➕ Новый матч\nЭтап: <b>{stage}</b>\n\nШаг 2/7. Введи дату (ДД/ММ/ГГГГ):"
    )
    await call.answer()


@router.message(AdminStates.match_date)
async def st_match_date(message: Message, state: FSMContext):
    moment = parse_match_datetime(clean(message.text or ""), "00:00")
    if moment is None:
        await message.answer("Не смог разобрать дату. Формат: 25/12/2026.")
        return
    await state.update_data(date=moment.strftime("%d/%m/%Y"))
    await state.set_state(AdminStates.match_time)
    await message.answer("Шаг 3/7. Введи время начала (ЧЧ:ММ):")


@router.message(AdminStates.match_time)
async def st_match_time(message: Message, state: FSMContext):
    moment = parse_match_datetime("01/01/2000", clean(message.text or ""))
    if moment is None:
        await message.answer("Не смог разобрать время. Формат: 19:30.")
        return
    await state.update_data(time=moment.strftime("%H:%M"))
    await state.set_state(AdminStates.match_team_a)
    await message.answer("Шаг 4/7. Введи название <b>команды А</b>:")


@router.message(AdminStates.match_team_a)
async def st_match_team_a(message: Message, state: FSMContext):
    name = sanitize(message.text or "", config.TEAM_MAX)
    if not name:
        await message.answer("Пусто. Введи название команды А.")
        return
    await state.update_data(team_a=name)
    await state.set_state(AdminStates.match_team_b)
    await message.answer("Шаг 5/7. Введи название <b>команды Б</b>:")


@router.message(AdminStates.match_team_b)
async def st_match_team_b(message: Message, state: FSMContext):
    name = sanitize(message.text or "", config.TEAM_MAX)
    if not name:
        await message.answer("Пусто. Введи название команды Б.")
        return
    await state.update_data(team_b=name)
    await state.set_state(AdminStates.match_branch_a)
    await message.answer(
        "Шаг 6/7. Выбери <b>филиал команды А</b>:",
        reply_markup=kb.branch_pick_kb("A"),
    )


def _match_preview(data) -> str:
    return (
        "➕ <b>Проверь матч</b>\n\n"
        f"Этап: <b>{esc(data.get('stage', ''))}</b>\n"
        f"Дата: <b>{esc(data.get('date', ''))}</b>\n"
        f"Время: <b>{esc(data.get('time', ''))}</b>\n"
        f"Команда А: <b>{esc(data.get('team_a', ''))}</b> "
        f"({esc(data.get('branch_a') or '—')})\n"
        f"Команда Б: <b>{esc(data.get('team_b', ''))}</b> "
        f"({esc(data.get('branch_b') or '—')})\n\n"
        "Сохранить и разослать участникам?"
    )


@router.callback_query(F.data.startswith("mbranch:"))
async def cb_mbranch(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        await call.answer("Только для админов", show_alert=True)
        return
    _, side, val = call.data.split(":")
    if val == "skip":
        branch = ""
    else:
        try:
            branch = config.BRANCHES[int(val)]
        except (IndexError, ValueError):
            await call.answer("Ошибка филиала", show_alert=True)
            return
    if side == "A":
        await state.update_data(branch_a=branch)
        await state.set_state(AdminStates.match_branch_b)
        await call.message.edit_text(
            f"Филиал команды А: <b>{esc(branch) or '—'}</b>\n\n"
            "Шаг 7/7. Выбери <b>филиал команды Б</b>:",
            reply_markup=kb.branch_pick_kb("B"),
        )
    else:
        await state.update_data(branch_b=branch)
        await state.set_state(AdminStates.match_confirm)
        data = await state.get_data()
        await call.message.edit_text(
            _match_preview(data), reply_markup=kb.match_confirm_kb()
        )
    await call.answer()


@router.callback_query(F.data == "msave")
async def cb_msave(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        await call.answer("Только для админов", show_alert=True)
        return
    data = await state.get_data()
    if not all(
        data.get(key) for key in ("date", "time", "team_a", "team_b")
    ):
        await state.clear()
        await call.message.edit_text("Не хватает данных, отменено.")
        await call.answer()
        return
    mid = sheets.create_match(
        stage=data.get("stage", ""),
        date=data["date"],
        time=data["time"],
        team_a=data["team_a"],
        team_b=data["team_b"],
        branch_a=data.get("branch_a", ""),
        branch_b=data.get("branch_b", ""),
    )
    await state.clear()
    await call.message.edit_text(
        "✅ Матч сохранён в таблицу.\n"
        f"<b>{esc(data['team_a'])}</b> — <b>{esc(data['team_b'])}</b> "
        f"({esc(data['date'])} {esc(data['time'])})"
    )
    sent = await _announce_match(mid)
    await call.message.answer(f"📨 Анонс разослан участникам: {sent}.")
    await call.answer()


async def _announce_match(mid) -> int:
    from app.bot import bot
    from app.handlers.menu import _match_line
    from app.scheduler import _match_button

    match = sheets.get_match(mid)
    if not match:
        return 0
    text = "🏁 <b>Новый матч!</b>\n\n" + _match_line(match) + "\n\nУспей сделать прогноз:"
    markup = _match_button(mid)
    sent = 0
    for user in sheets.all_users():
        try:
            await bot.send_message(user.tg_id, text, reply_markup=markup)
            sent += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)
    return sent


# ============================================================ результат матча
@router.message(Command("result"))
async def cmd_result(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await _denied(message)
        return
    await state.clear()
    await _show_result_matches(message.answer)


async def _show_result_matches(answer):
    matches = [m for m in sheets.get_matches() if not m.resolved]
    matches.sort(key=lambda m: m.dt or DT_MAX)
    if not matches:
        await answer("Нет матчей без результата.")
        return
    await answer(
        "✅ Выбери матч, чтобы отметить победителя:",
        reply_markup=kb.result_matches_kb(matches),
    )


@router.callback_query(F.data.startswith("rres:"))
async def cb_rres(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        await call.answer("Только для админов", show_alert=True)
        return
    match = sheets.get_match(call.data.split(":", 1)[1])
    if not match:
        await call.answer("Матч не найден", show_alert=True)
        return
    if match.resolved:
        await call.answer("У матча уже есть результат", show_alert=True)
        return
    moment = f"{match.date} {match.time}".strip()
    await call.message.edit_text(
        f"✅ {esc(match.team_a)} — {esc(match.team_b)}\n🕒 {esc(moment)}\n\nКто победил?",
        reply_markup=kb.result_side_kb(match),
    )
    await call.answer()


@router.callback_query(F.data.startswith("rset:"))
async def cb_rset(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        await call.answer("Только для админов", show_alert=True)
        return
    _, mid, side = call.data.split(":")
    match = sheets.get_match(mid)
    if not match:
        await call.answer("Матч не найден", show_alert=True)
        return
    team = match.team_a if side == "A" else match.team_b
    sheets.set_result(match, team)
    _, _, score_map, _, _ = build_full_export()
    sheets.write_scores(score_map)
    schedule_scoreboard_refresh()
    await call.message.edit_text(
        f"✅ Результат записан: <b>{esc(match.team_a)}</b> — "
        f"<b>{esc(match.team_b)}</b>\n"
        f"🏆 Победитель: <b>{esc(team)}</b>\nБаллы пересчитаны."
    )
    await call.answer("Готово")


@router.message(Command("scoreboard"))
async def cmd_scoreboard(message: Message):
    if not _is_admin(message.from_user.id):
        await _denied(message)
        return
    await message.answer("⏳ Обновляю листы «Баллы» и по этапам...")
    count = refresh_scoreboard()
    await message.answer(
        f"✅ Готово: общий лист «{config.SHEET_SCORES}» + по одному листу "
        f"на каждый этап ({', '.join(config.STAGES)}). Участников: {count}."
    )


# ==================================================== админ-меню (callback'и)
@router.callback_query(F.data == "adm:result")
async def cb_adm_result(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        await call.answer("Только для админов", show_alert=True)
        return
    await state.clear()
    await _show_result_matches(call.message.answer)
    await call.answer()


@router.callback_query(F.data == "adm:scoreboard")
async def cb_adm_scoreboard(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        await call.answer("Только для админов", show_alert=True)
        return
    count = refresh_scoreboard()
    await call.message.answer(
        f"✅ Готово: лист «{config.SHEET_SCORES}» + по листу на каждый этап "
        f"({', '.join(config.STAGES)}). Участников: {count}."
    )
    await call.answer()


@router.callback_query(F.data == "adm:refresh")
async def cb_adm_refresh(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        await call.answer("Только для админов", show_alert=True)
        return
    _, _, score_map, rating, _ = build_full_export()
    sheets.write_scores(score_map)
    await call.message.answer(
        f"✅ Пересчитал баллы: {len(score_map)} прогнозов, {len(rating)} участников."
    )
    await call.answer()


@router.callback_query(F.data == "adm:export")
async def cb_adm_export(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        await call.answer("Только для админов", show_alert=True)
        return
    await call.answer("Формирую...")
    participants, eligible = export_results()
    schedule_scoreboard_refresh()
    await call.message.answer(
        f"✅ Готово!\n"
        f"Лист «{config.SHEET_RESULTS}»: {participants} участников (ФИО без дублей).\n"
        f"Лист «{config.SHEET_DRAW}»: {eligible} человек с порогом "
        f"{int(config.DRAW_THRESHOLD * 100)}%+.\n"
        f"Лист «{config.SHEET_SCORES}» + лист каждого этапа обновлены."
    )


@router.callback_query(F.data == "adm:stats")
async def cb_adm_stats(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        await call.answer("Только для админов", show_alert=True)
        return
    await call.message.answer(_stats_text())
    await call.answer()


@router.callback_query(F.data == "adm:broadcast")
async def cb_adm_broadcast(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        await call.answer("Только для админов", show_alert=True)
        return
    await state.set_state(AdminStates.broadcast)
    await call.message.answer(
        "Введи текст рассылки (поддерживается HTML) или /cancel для отмены."
    )
    await call.answer()
