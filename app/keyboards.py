from aiogram.types import ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

import config
from app.utils import format_dt


def regions_kb():
    kb = ReplyKeyboardBuilder()
    for branch in config.BRANCHES:
        kb.button(text=branch)
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True, one_time_keyboard=True)


def remove_kb():
    return ReplyKeyboardRemove()


def main_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Ближайшие матчи", callback_data="menu:matches")
    kb.button(text="🔮 Мои прогнозы", callback_data="menu:my_preds")
    kb.button(text="🏆 Рейтинг", callback_data="menu:rating")
    kb.button(text="👤 Профиль", callback_data="menu:profile")
    kb.adjust(2, 2)
    return kb.as_markup()


def matches_kb(matches):
    kb = InlineKeyboardBuilder()
    for match in matches:
        kb.button(
            text=f"{match.team_a} — {match.team_b}",
            callback_data=f"match:{match.mid}",
        )
    kb.button(text="⬅️ В меню", callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()


def match_kb(match):
    kb = InlineKeyboardBuilder()
    kb.button(text=f"✅ {match.team_a}", callback_data=f"pred:{match.mid}:A")
    kb.button(text=f"✅ {match.team_b}", callback_data=f"pred:{match.mid}:B")
    kb.button(text="⬅️ К списку матчей", callback_data="menu:matches")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def back_to_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ В меню", callback_data="menu:home")
    return kb.as_markup()


# ------------------------------------------------------------------ админ ---
def admin_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Новый матч", callback_data="adm:add")
    kb.button(text="✅ Результат матча", callback_data="adm:result")
    kb.button(text="🧮 Обновить «Баллы»", callback_data="adm:scoreboard")
    kb.button(text="🔄 Пересчитать баллы", callback_data="adm:refresh")
    kb.button(text="📊 Итоги (export)", callback_data="adm:export")
    kb.button(text="📈 Статистика", callback_data="adm:stats")
    kb.button(text="📢 Рассылка", callback_data="adm:broadcast")
    kb.adjust(2, 2, 2, 1)
    return kb.as_markup()


def stages_kb():
    kb = InlineKeyboardBuilder()
    for idx, stage in enumerate(config.STAGES):
        kb.button(text=stage, callback_data=f"mstage:{idx}")
    kb.button(text="✖️ Отмена", callback_data="mcancel")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def branch_pick_kb(side):
    kb = InlineKeyboardBuilder()
    for idx, branch in enumerate(config.BRANCHES):
        kb.button(text=branch, callback_data=f"mbranch:{side}:{idx}")
    kb.button(text="⏭ Без филиала", callback_data=f"mbranch:{side}:skip")
    kb.button(text="✖️ Отмена", callback_data="mcancel")
    kb.adjust(2)
    return kb.as_markup()


def match_confirm_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Сохранить и разослать", callback_data="msave")
    kb.button(text="✖️ Отмена", callback_data="mcancel")
    kb.adjust(1)
    return kb.as_markup()


def result_matches_kb(matches):
    kb = InlineKeyboardBuilder()
    for match in matches:
        label = f"{match.team_a} — {match.team_b}"
        if match.dt:
            label = f"{format_dt(match.dt)} · {label}"
        kb.button(text=label, callback_data=f"rres:{match.mid}")
    kb.button(text="✖️ Закрыть", callback_data="rclose")
    kb.adjust(1)
    return kb.as_markup()


def result_side_kb(match):
    kb = InlineKeyboardBuilder()
    kb.button(text=f"🏆 {match.team_a}", callback_data=f"rset:{match.mid}:A")
    kb.button(text=f"🏆 {match.team_b}", callback_data=f"rset:{match.mid}:B")
    kb.button(text="✖️ Отмена", callback_data="rclose")
    kb.adjust(1, 1, 1)
    return kb.as_markup()
