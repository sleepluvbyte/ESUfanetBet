from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    fio = State()
    region = State()


class AdminStates(StatesGroup):
    broadcast = State()
    # Создание матча (менеджер заводит через бота)
    match_stage = State()
    match_date = State()
    match_time = State()
    match_team_a = State()
    match_team_b = State()
    match_branch_a = State()
    match_branch_b = State()
    match_confirm = State()
