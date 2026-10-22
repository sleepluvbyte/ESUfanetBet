from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import config
from app import keyboards as kb
from app.sheets import sheets
from app.states import Registration
from app.utils import clean, esc, normalize, sanitize

router = Router()

WELCOME_NEW = (
    "🏆 <b>Уфанет: Турнир по CS 2</b>\n\n"
    "Добро пожаловать! Здесь ты прогнозируешь исходы матчей и получаешь баллы.\n\n"
    "Давай зарегистрируемся — это нужно всего один раз.\n"
    "Введи своё <b>ФИО</b> (например: Иванов Иван Иванович):"
)

WELCOME_BACK = "С возвращением, <b>{fio}</b>! Выбери действие:"


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = sheets.get_user(message.from_user.id)
    if user:
        await message.answer(
            WELCOME_BACK.format(fio=esc(user.fio)),
            reply_markup=kb.main_menu_kb(),
        )
        return
    await state.set_state(Registration.fio)
    await message.answer(WELCOME_NEW)


@router.message(Registration.fio)
async def reg_fio(message: Message, state: FSMContext):
    fio = sanitize(message.text or "", config.FIO_MAX)
    if len(fio.split()) < 2 or len(fio) < 5:
        await message.answer(
            "Похоже, это не ФИО. Введи полностью: Фамилия Имя Отчество."
        )
        return
    await state.update_data(fio=fio)
    await state.set_state(Registration.region)
    await message.answer(
        "Отлично! Теперь выбери свой филиал:", reply_markup=kb.regions_kb()
    )


@router.message(Registration.region)
async def reg_region(message: Message, state: FSMContext):
    text = clean(message.text or "")
    branch = next(
        (b for b in config.BRANCHES if normalize(b) == normalize(text)), None
    )
    if branch is None:
        await message.answer(
            "Пожалуйста, выбери филиал из списка кнопок ниже.",
            reply_markup=kb.regions_kb(),
        )
        return
    data = await state.get_data()
    fio = data.get("fio", "")
    username = message.from_user.username or ""
    sheets.add_user(message.from_user.id, fio, branch, username)
    await state.clear()
    await message.answer(
        f"Готово, <b>{esc(fio)}</b>! Филиал: <b>{esc(branch)}</b>.\n"
        "Прогнозы и напоминания будут приходить сюда.",
        reply_markup=kb.remove_kb(),
    )
    await message.answer("Главное меню:", reply_markup=kb.main_menu_kb())


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "Команды:\n"
        "/start — регистрация и меню\n"
        "/matches — ближайшие матчи\n"
        "/rating — общий рейтинг\n"
        "/me — мой профиль и баллы\n"
        "/id — мой Telegram ID"
    )


@router.message(Command("id"))
async def cmd_id(message: Message):
    username = f"@{message.from_user.username}" if message.from_user.username else "—"
    await message.answer(
        f"Твой Telegram ID: <code>{message.from_user.id}</code>\nUsername: {username}"
    )
