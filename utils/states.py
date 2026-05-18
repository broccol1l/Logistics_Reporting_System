from aiogram.fsm.state import State, StatesGroup

class Register(StatesGroup):
    name = State()
    phone = State()

class EditName(StatesGroup):
    name = State()

class DeliveryState(StatesGroup):
    object_name = State()
    choosing_product = State()
    weight_plan = State()
    weight_fact = State()
    waiting_fuel = State()
    waiting_other_amount = State()
    waiting_other_comment = State()


class AdminState(StatesGroup):
    waiting_product_name = State()
    waiting_product_unit = State()
    waiting_p_sadik_add = State()
    waiting_p_zakup_add = State()

    waiting_broadcast_text = State()


class AdminEdit(StatesGroup):
    waiting_p_sadik_edit = State()
    waiting_p_zakup_edit = State()
    waiting_name_edit = State()
    waiting_shift_fuel = State()

    waiting_shift_other_exp = State()
    waiting_shift_other_comment = State()

class KGState(StatesGroup):
    waiting_kg_name = State()
    waiting_kg_edit_name = State()


class AdminStatsState(StatesGroup):
    waiting_custom_period = State()