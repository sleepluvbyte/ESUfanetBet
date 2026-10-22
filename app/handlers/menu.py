from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app import keyboards as kb
from app.scoring import compute_rating, schedule_scoreboard_refresh
from app.sheets import sheets
from app.utils import DT_MAX, esc, format_dt, now_local

router = Router()

NOT_REGISTERED = "Сначала зарегистрируйся командой /start."


def _upcoming(matches, now):
    result = [
        match
        for match in matches
        if not match.resolved and (match.dt is None or match.dt > now)
    ]
    result.sort(key=lambda m: m.dt or DT_MAX)
    return result


def _match_line(match):
    moment = format_dt(match.dt) if match.dt else f"{match.date} {match.time}".strip()
    parts = [f"🕒 {esc(moment)}"]
    if match.stage:
        parts.append(esc(match.stage))
    if match.region:
        parts.append(esc(match.region))
    if match.branch_a or match.branch_b:
        parts.append(f"{esc(match.branch_a)} / {esc(match.branch_b)}")
    return (
        f"<b>{esc(match.team_a)}</b> — <b>{esc(match.team_b)}</b>\n"
        + " · ".join(parts)
    )


def _match_text(match, user_pred=None):
    lines = [_match_line(match), ""]
    if match.resolved:
        lines.append(
            f"🏁 Матч завершён. Победитель: <b>{esc(match.winner_team)}</b>"
        )
    if user_pred:
        lines.append(f"Твой прогноз: <b>{esc(user_pred.prediction)}</b>")
        if match.resolved:
            status = (
                "✅ угадал (+1 балл)"
                if match.is_correct(user_pred.prediction)
                else "❌ не угадал"
            )
            lines.append(status)
    elif not match.resolved:
        lines.append("Прогноз не сделан. Выбери победителя ниже:")
    return "\n".join(lines)


def _rating_text(rating, total_matches, highlight_tg=None):
    header = (
        f"🏆 <b>Рейтинг участников</b>\n"
        f"Сыграно матчей: {total_matches}\n\n"
    )
    if not rating:
        return header + "Пока нет участников."
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = []
    for place, row in enumerate(rating[:20], start=1):
        medal = medals.get(place, f"{place}.")
        you = " ← ты" if highlight_tg and highlight_tg in row.tg_ids else ""
        lines.append(
            f"{medal} {esc(row.user.fio)} — <b>{row.points}</b> б ({row.correct}/{row.total}){you}"
        )
    text = header + "\n".join(lines)
    if highlight_tg:
        mine = next((r for r in rating if highlight_tg in r.tg_ids), None)
        if mine and mine not in rating[:20]:
            place = rating.index(mine) + 1
            text += (
                f"\n\nТы на {place} месте: <b>{mine.points}</b> б "
                f"({mine.correct}/{mine.total})"
            )
    return text


async def _safe_edit(call: CallbackQuery, text, markup=None):
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except Exception:
        await call.message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "menu:home")
async def cb_home(call: CallbackQuery):
    user = sheets.get_user(call.from_user.id)
    if not user:
        await call.answer(NOT_REGISTERED, show_alert=True)
        return
    await _safe_edit(call, f"Главное меню, <b>{esc(user.fio)}</b>:", kb.main_menu_kb())
    await call.answer()


@router.callback_query(F.data == "menu:matches")
async def cb_matches(call: CallbackQuery):
    matches = _upcoming(sheets.get_matches(), now_local())
    if not matches:
        await _safe_edit(
            call, "Пока нет предстоящих матчей. Заходи позже!", kb.back_to_menu_kb()
        )
        await call.answer()
        return
    await _safe_edit(
        call,
        "📅 <b>Ближайшие матчи</b>\nВыбери матч и сделай прогноз:",
        kb.matches_kb(matches),
    )
    await call.answer()


@router.callback_query(F.data.startswith("match:"))
async def cb_match(call: CallbackQuery):
    mid = call.data.split(":", 1)[1]
    match = sheets.get_match(mid)
    if not match:
        await call.answer("Матч не найден", show_alert=True)
        return
    user_pred = sheets.get_prediction(call.from_user.id, mid)
    await _safe_edit(call, _match_text(match, user_pred), kb.match_kb(match))
    await call.answer()


@router.callback_query(F.data.startswith("pred:"))
async def cb_predict(call: CallbackQuery):
    _, mid, side = call.data.split(":")
    match = sheets.get_match(mid)
    if not match:
        await call.answer("Матч не найден", show_alert=True)
        return
    if match.resolved:
        await call.answer("Матч уже завершён, прогнозы закрыты.", show_alert=True)
        return
    if match.dt and match.dt < now_local():
        await call.answer("Матч уже начался, прогнозы закрыты.", show_alert=True)
        return
    team = match.team_a if side == "A" else match.team_b
    sheets.set_prediction(call.from_user.id, mid, team)
    # Сразу обновляем матрицу «Баллы», чтобы прогноз участника появился в таблице.
    schedule_scoreboard_refresh()
    user_pred = sheets.get_prediction(call.from_user.id, mid)
    await _safe_edit(call, _match_text(match, user_pred), kb.match_kb(match))
    await call.answer(f"Прогноз: {team}")


@router.callback_query(F.data == "menu:my_preds")
async def cb_my_preds(call: CallbackQuery):
    user = sheets.get_user(call.from_user.id)
    if not user:
        await call.answer(NOT_REGISTERED, show_alert=True)
        return
    matches = {m.mid: m for m in sheets.get_matches()}
    preds = [p for p in sheets.all_predictions() if p.tg_id == call.from_user.id]
    if not preds:
        await _safe_edit(
            call, "🔮 Ты ещё не сделал ни одного прогноза.", kb.back_to_menu_kb()
        )
        await call.answer()
        return
    lines = ["🔮 <b>Мои прогнозы</b>", ""]
    correct = 0
    for pred in preds:
        match = matches.get(pred.mid)
        if not match:
            continue
        moment = format_dt(match.dt) if match.dt else f"{match.date} {match.time}"
        head = f"{esc(moment)} · {esc(match.team_a)} vs {esc(match.team_b)}"
        if match.resolved:
            if match.is_correct(pred.prediction):
                correct += 1
                lines.append(f"✅ {head}\n   прогноз: {esc(pred.prediction)} (+1)")
            else:
                lines.append(f"❌ {head}\n   прогноз: {esc(pred.prediction)}")
        else:
            lines.append(f"⏳ {head}\n   прогноз: {esc(pred.prediction)}")
    lines.append("")
    lines.append(f"Верных прогнозов: <b>{correct}</b>")
    await _safe_edit(call, "\n".join(lines), kb.back_to_menu_kb())
    await call.answer()


@router.callback_query(F.data == "menu:rating")
async def cb_rating(call: CallbackQuery):
    rating, _, total = compute_rating()
    await _safe_edit(
        call, _rating_text(rating, total, call.from_user.id), kb.back_to_menu_kb()
    )
    await call.answer()


@router.callback_query(F.data == "menu:profile")
async def cb_profile(call: CallbackQuery):
    user = sheets.get_user(call.from_user.id)
    if not user:
        await call.answer(NOT_REGISTERED, show_alert=True)
        return
    rating, _, total = compute_rating()
    mine = next((r for r in rating if user.tg_id in r.tg_ids), None)
    place = rating.index(mine) + 1 if mine else "-"
    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"ФИО: <b>{esc(user.fio)}</b>\n"
        f"Филиал: <b>{esc(user.region)}</b>\n"
        f"Баллы: <b>{mine.points if mine else 0}</b>\n"
        f"Угадано: {mine.correct if mine else 0} из {total}\n"
        f"Место в рейтинге: <b>{place}</b>"
    )
    await _safe_edit(call, text, kb.back_to_menu_kb())
    await call.answer()


@router.message(Command("matches"))
async def cmd_matches(message: Message):
    matches = _upcoming(sheets.get_matches(), now_local())
    if not matches:
        await message.answer("Пока нет предстоящих матчей.")
        return
    await message.answer(
        "📅 <b>Ближайшие матчи</b>\nВыбери матч:", kb.matches_kb(matches)
    )


@router.message(Command("rating"))
async def cmd_rating(message: Message):
    rating, _, total = compute_rating()
    await message.answer(_rating_text(rating, total, message.from_user.id))


@router.message(Command("me"))
async def cmd_me(message: Message):
    user = sheets.get_user(message.from_user.id)
    if not user:
        await message.answer(NOT_REGISTERED)
        return
    rating, _, total = compute_rating()
    mine = next((r for r in rating if user.tg_id in r.tg_ids), None)
    place = rating.index(mine) + 1 if mine else "-"
    await message.answer(
        f"👤 <b>{esc(user.fio)}</b> ({esc(user.region)})\n"
        f"Баллы: <b>{mine.points if mine else 0}</b>\n"
        f"Угадано: {mine.correct if mine else 0} из {total}\n"
        f"Место: <b>{place}</b>"
    )
