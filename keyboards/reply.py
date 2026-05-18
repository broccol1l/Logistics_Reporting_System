from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from utils.constants import KINDERGARTENS


def get_register_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )


from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu_kb(is_admin: bool = False):
    buttons = [
        [KeyboardButton(text="📦 Yuk qo'shish")],#📦  Добавить отгрузку
        [KeyboardButton(text="📊 Hisobotlarim"), KeyboardButton(text="🏁 Smenani yopish")],#📊  Мои отчеты"
        [KeyboardButton(text="📝 Ismni o'zgartirish")]# 📝 Изменить имя"
    ]

    if is_admin:
        buttons.append([KeyboardButton(text="⚙️ Admin paneli")]) # ⚙️ Админ-панель

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Amalni tanlang..." # Выберите действие...
    )

def get_objects_kb():
    builder = ReplyKeyboardBuilder()

    for name in KINDERGARTENS:
        builder.button(text=name)

    builder.adjust(2)

    return builder.as_markup(resize_keyboard=True)
