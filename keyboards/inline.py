import math
from aiogram.filters.callback_data import CallbackData
from database.models import Product
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta

class KGOrderCallback(CallbackData, prefix="kg"):
    action: str
    kg_id: int
    page: int

class ProductCallback(CallbackData, prefix="prod"):
    action: str
    prod_id: int
    page: int


# --- КЛАВИАТУРА САДИКОВ ---

def get_kg_paging_kb(kg_list, page: int = 0):
    builder = InlineKeyboardBuilder()
    items_per_page = 6

    start = page * items_per_page
    end = start + items_per_page
    current_items = kg_list[start:end]

    for kg in current_items:
        builder.button(
            text=kg.name,
            callback_data=KGOrderCallback(action="select", kg_id=kg.id, page=page)
        )

    builder.adjust(1)

    if len(kg_list) > items_per_page:
        nav_row = []
        total_pages = math.ceil(len(kg_list) / items_per_page)

        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="⬅️", callback_data=KGOrderCallback(action="nav", kg_id=0, page=page - 1).pack()))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="none"))

        nav_row.append(InlineKeyboardButton(text=f"{page + 1} / {total_pages}", callback_data="none"))

        if end < len(kg_list):
            nav_row.append(InlineKeyboardButton(
                text="➡️", callback_data=KGOrderCallback(action="nav", kg_id=0, page=page + 1).pack()))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="none"))

        builder.row(*nav_row)

    return builder.as_markup()


# --- КЛАВИАТУРА ТОВАРОВ ---

def get_products_paging_kb(products_list, page: int = 0):
    builder = InlineKeyboardBuilder()
    items_per_page = 10 # Товаров можно побольше на экран

    start = page * items_per_page
    end = start + items_per_page
    current_items = products_list[start:end]

    for prod in current_items:
        builder.button(
            text=f"{prod.name} ({prod.unit})",
            callback_data=ProductCallback(action="select", prod_id=prod.id, page=page)
        )

    builder.adjust(1)

    if len(products_list) > items_per_page:
        nav_row = []
        total_pages = math.ceil(len(products_list) / items_per_page)

        if page > 0:
            nav_row.append(InlineKeyboardButton(
                text="⬅️", callback_data=ProductCallback(action="nav", prod_id=0, page=page - 1).pack()))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="none"))

        nav_row.append(InlineKeyboardButton(text=f"{page + 1} / {total_pages}", callback_data="none"))

        if end < len(products_list):
            nav_row.append(InlineKeyboardButton(
                text="➡️", callback_data=ProductCallback(action="nav", prod_id=0, page=page + 1).pack()))
        else:
            nav_row.append(InlineKeyboardButton(text=" ", callback_data="none"))

        builder.row(*nav_row)

    return builder.as_markup()


# --- КЛАВИАТУРА ЦИКЛА ---

def get_loop_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Yana mahsulot qo'shish", callback_data="add_more_prod") # ➕ Добавить еще товар"
    builder.button(text="✅ Bog'chani yakunlash", callback_data="finish_this_kg") # ✅ Завершить этот садик"

    # НОВАЯ КНОПКА:
    builder.button(text="🗓 Smena sanasini tuzatish", callback_data="change_shift_date_start") # 🗓 Исправить дату смены

    builder.button(text="🔍 Ko'rish / Bog'chani o'chirish", callback_data="manage_current_shift") # 🔍 Просмотр / Удалить садик
    builder.button(text="🏁 Smenani yopish", callback_data="go_to_close_shift") # 🏁 Завершить смену
    builder.adjust(1)
    return builder.as_markup()


def get_reports_paging_kb(shifts, page: int = 0, limit: int = 5):
    builder = InlineKeyboardBuilder()

    for shift in shifts:
        date_str = shift.opened_at.strftime("%d.%m.%Y")

        builder.button(
            text=f"📅 {date_str} | {shift.total_sum:,} сум",
            callback_data=f"view_rep:{shift.id}"
        )

    builder.adjust(1)
    return builder.as_markup()


# --- КЛАВИАТУРА ДЕТАЛЕЙ ОТЧЕТА ---
def get_report_details_kb(shift_id: int):
    builder = InlineKeyboardBuilder()

    builder.button(text="📗 Excel", callback_data=f"export_xlsx:{shift_id}")
    builder.button(text="📄 PDF", callback_data=f"export_pdf:{shift_id}")

    builder.button(text="✏️ Tahrirlash (qo'shish/o'chirish)", callback_data=f"edit_rep:{shift_id}") # "✏️ Редактировать (добавить/удалить)"

    builder.button(text="🗑 Hisobotni o'chirish", callback_data=f"del_rep:{shift_id}") # "🗑 Удалить отчет"
    builder.button(text="⬅️ Ro'yxatga qaytish", callback_data="rep_page:0") # "⬅️ Назад к списку"

    builder.adjust(2, 1, 2)
    return builder.as_markup()


def get_date_selection_kb():
    builder = InlineKeyboardBuilder()
    today = datetime.now().strftime("%d.%m")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%d.%m")

    builder.button(text=f"📅 Bugun ({today})", callback_data="set_date:today") # Сегодня
    builder.button(text=f"📅 Kecha ({yesterday})", callback_data="set_date:yesterday") # Вчера
    builder.adjust(1)
    return builder.as_markup()


def get_manage_current_kb(kgs_dict):
    builder = InlineKeyboardBuilder()
    for kg_id, kg_name in kgs_dict.items():
        builder.button(text=f"❌ {kg_name}ni o'chirish", callback_data=f"del_kg_curr:{kg_id}") # # ❌ Удалить {kg_name}

    builder.button(text="⬅️ Ortga", callback_data="back_to_loop")
    builder.adjust(1)
    return builder.as_markup()


from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def admin_main_kb():
    buttons = [
        [InlineKeyboardButton(text="📦 Mahsulotlar va Narxlar", callback_data="admin_products")], # "📦 Товары и Цены"
        [InlineKeyboardButton(text="🏫 Bog'chalar (Obyektlar)", callback_data="admin_kindergartens")], # "🏫 Садики (Объекты)"
        [InlineKeyboardButton(text="👥 Haydovchilar va Hisobotlar", callback_data="admin_drivers")], # "👥 Водители и Отчеты"
        [InlineKeyboardButton(text="📊 Umumiy Analitika", callback_data="admin_stats")], # "📊 Общая Аналитика"
        [InlineKeyboardButton(text="⬅️ Haydovchi menyusiga qaytish", callback_data="admin_exit")] # "⬅️ Выйти в меню водителя"
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ADMIN
def get_products_list_kb(products: list[Product], page: int = 0):
    builder = InlineKeyboardBuilder()
    limit = 6
    start = page * limit
    end = start + limit

    for product in products[start:end]:
        btn_text = f"{product.name} ({int(product.price_sadik)}/{int(product.price_zakup)})"
        builder.row(InlineKeyboardButton(text=btn_text, callback_data=f"adm_prod_view:{product.id}"))

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Ortga", callback_data=f"adm_prod_page:{page - 1}"))

    if end < len(products):
        nav_buttons.append(InlineKeyboardButton(text="Oldinga ➡️", callback_data=f"adm_prod_page:{page + 1}"))

    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(InlineKeyboardButton(text="➕ Mahsulot qo'shish", callback_data="adm_prod_add"))
    builder.row(InlineKeyboardButton(text="🏠 Boshiga", callback_data="admin_home"))

    return builder.as_markup()


def get_product_card_kb(product_id: int):
    builder = InlineKeyboardBuilder()

    builder.row(InlineKeyboardButton(text="💰 Bog'cha narxi", callback_data=f"adm_prod_edit:p_sadik:{product_id}"))# "💰 Цена садика"
    builder.row(InlineKeyboardButton(text="📉 Xarid narxi", callback_data=f"adm_prod_edit:p_zakup:{product_id}"))# "📉 Цена закупа"
    builder.row(InlineKeyboardButton(text="✏️ Nomi", callback_data=f"adm_prod_edit:name:{product_id}"))# "✏️ Название"
    builder.row(InlineKeyboardButton(text="🗑 Mahsulotni o'chirish", callback_data=f"adm_prod_delete:{product_id}"))# "🗑 Удалить товар"

    builder.row(InlineKeyboardButton(text="⬅️ Ro'yxatga qaytish", callback_data="admin_products"))

    return builder.as_markup()

def get_cancel_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_cancel_edit"))
    return builder.as_markup()

def get_units_kb():
    builder = InlineKeyboardBuilder()
    for unit in ["кг", "литр", "шт"]:
        builder.button(text=unit, callback_data=f"unit_set:{unit}")
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_cancel_edit"))
    return builder.as_markup()


# --- КЛАВИАТУРЫ ДЛЯ САДИКОВ ---

def get_kg_list_kb(kg_list: list, page: int = 0):
    builder = InlineKeyboardBuilder()
    limit = 6
    start = page * limit
    end = start + limit

    # Садики
    for kg in kg_list[start:end]:
        builder.row(InlineKeyboardButton(text=f"🏫 {kg.name}", callback_data=f"adm_kg_view:{kg.id}"))

    # Ряд навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Ortga", callback_data=f"adm_kg_page:{page - 1}"))
    if end < len(kg_list):
        nav_buttons.append(InlineKeyboardButton(text="Oldinga ➡️", callback_data=f"adm_kg_page:{page + 1}"))

    if nav_buttons:
        builder.row(*nav_buttons)

    # Управление (всегда отдельными рядами снизу)

    builder.row(InlineKeyboardButton(text="➕ Bog'cha qo'shish", callback_data="adm_kg_add"))
    builder.row(InlineKeyboardButton(text="🏠 Boshiga", callback_data="admin_home")) # 🏠 Boshiga

    return builder.as_markup()


def get_kg_card_kb(kg_id: int):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Nomini o'zgartirish", callback_data=f"adm_kg_edit:{kg_id}"))
    builder.row(InlineKeyboardButton(text="🗑 Bog'chani o'chirish", callback_data=f"adm_kg_delete:{kg_id}"))
    builder.row(InlineKeyboardButton(text="⬅️ Ro'yxatga qaytish", callback_data="admin_kindergartens"))
    return builder.as_markup()


# --- КЛАВИАТУРЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ---

def get_users_list_kb(users: list, page: int = 0):
    builder = InlineKeyboardBuilder()
    limit = 6
    start = page * limit
    end = start + limit

    for user in users[start:end]:
        # Статус на основе твоих полей
        if user.is_admin:
            status = "🛡️"
        elif user.is_blocked:
            status = "🚫"
        else:
            status = "🚚"

        name = user.full_name or f"ID: {user.id}"
        builder.row(InlineKeyboardButton(
            text=f"{status} {name}",
            callback_data=f"adm_user_view:{user.id}")
        )

    # Пагинация (оставляем как была)
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Ortga", callback_data=f"adm_user_page:{page - 1}"))
    if end < len(users):
        nav_buttons.append(InlineKeyboardButton(text="Oldinga ➡️", callback_data=f"adm_user_page:{page + 1}"))

    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(InlineKeyboardButton(text="🏠 Boshiga", callback_data="admin_home"))
    return builder.as_markup()


def get_user_card_kb(user_id: int, is_admin: bool, is_blocked: bool):
    builder = InlineKeyboardBuilder()

    # Кнопки смены прав (Админ / Не админ)
    if is_admin:
        builder.row(InlineKeyboardButton(text="👤 Admin huquqini olish", callback_data=f"adm_user_set:demote:{user_id}"))
    else:
        builder.row(InlineKeyboardButton(text="🛡️ Admin qilish", callback_data=f"adm_user_set:promote:{user_id}"))

    # Кнопки блокировки (Бан / Разбан)
    if is_blocked:
        builder.row(InlineKeyboardButton(text="✅ Blokdan chiqarish", callback_data=f"adm_user_set:unblock:{user_id}"))
    else:
        builder.row(InlineKeyboardButton(text="🚫 Bloklash", callback_data=f"adm_user_set:block:{user_id}"))

    builder.row(InlineKeyboardButton(text="📂 Hisobotlar tarixi", callback_data=f"adm_history:{user_id}"))
    builder.row(InlineKeyboardButton(text="⬅️ Foydalanuvchilar ro'yxatiga", callback_data="admin_drivers"))
    return builder.as_markup()


# Клавиатура со списком дат (смен) водителя для АДМИНА
def get_admin_user_history_kb(shifts, user_id: int, page: int = 0, limit: int = 5):
    builder = InlineKeyboardBuilder()

    for shift in shifts:
        date_str = shift.opened_at.strftime("%d.%m.%Y")
        # Текст: Дата | Сумма (чтобы админ сразу видел масштаб)
        builder.button(
            text=f"📅 {date_str} | {shift.total_sum:,} сум",
            callback_data=f"adm_view_rep:{shift.id}"
        )

    builder.adjust(1)

    # Навигация (если смен много)
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Ortga", callback_data=f"adm_rep_page:{user_id}:{page - 1}"))
    if len(shifts) == limit:
        nav_buttons.append(InlineKeyboardButton(text="Oldinga ➡️", callback_data=f"adm_rep_page:{user_id}:{page + 1}"))

    if nav_buttons:
        builder.row(*nav_buttons)

    # Кнопка возврата именно в карточку этого юзера
    builder.row(InlineKeyboardButton(text="⬅️ Kartochkaga qaytish", callback_data=f"adm_user_view:{user_id}"))

    return builder.as_markup()


# Клавиатура просмотра отчета (инструменты админа)
def get_admin_report_tools_kb(shift_id: int, user_id: int):
    builder = InlineKeyboardBuilder()
    # ВАЖНО: callback должен быть adm_edit_rep, а не adm_edit_menu
    builder.row(
        InlineKeyboardButton(text="✏️ Tahrirlash (Qo'shish/O'chirish)", callback_data=f"adm_edit_rep:{shift_id}"))

    builder.row(
        InlineKeyboardButton(text="📗 Excel", callback_data=f"export_xlsx:{shift_id}"),
        InlineKeyboardButton(text="📄 PDF", callback_data=f"export_pdf:{shift_id}")
    )

    builder.row(InlineKeyboardButton(text="🗑 Hisobotni o'chirish", callback_data=f"adm_del_rep:{shift_id}"))
    builder.row(InlineKeyboardButton(text="⬅️ Ortga", callback_data=f"adm_history:{user_id}"))
    builder.adjust(1, 2, 1, 1)
    return builder.as_markup()


# Добавь это в keyboards/inline.py

def get_admin_edit_menu_kb(shift_id: int):
    builder = InlineKeyboardBuilder()
    # Обрати внимание на префиксы adm_
    builder.button(text="➕ Mahsulotlar qo'shish", callback_data=f"adm_add_start:{shift_id}")
    builder.button(text="🔍 Ko'rish / Bog'chalarni o'chirish", callback_data=f"adm_manage_shift:{shift_id}")
    builder.button(text="🏁 Tuzatishlarni yakunlash", callback_data=f"adm_finish_edit:{shift_id}")
    builder.adjust(1)
    return builder.as_markup()


# Список садиков для удаления (для админа)
def get_admin_manage_kgs_kb(kgs_dict, shift_id: int):
    builder = InlineKeyboardBuilder()
    for kg_id, kg_name in kgs_dict.items():
        # Специфический колбэк для админа
        builder.button(text=f"❌ {kg_name}ni o'chirish", callback_data=f"adm_del_kg:{shift_id}:{kg_id}")

    builder.button(text="⬅️ Ortga", callback_data=f"adm_view_rep:{shift_id}")
    builder.adjust(1)
    return builder.as_markup()


# В keyboards/inline.py

# 1. Главное меню редактирования (добавил кнопку "Добавить садик")
def get_admin_edit_loop_kb(shift_id: int):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏫 Yangi bog'cha qo'shish", callback_data=f"adm_add_kg_start:{shift_id}"))
    builder.row(InlineKeyboardButton(text="🔍 Ko'rish / Bog'chalarni o'chirish", callback_data=f"adm_manage_shift:{shift_id}"))
    builder.row(InlineKeyboardButton(text="🗓 Smena sanasini o'zgartirish", callback_data=f"adm_change_date:{shift_id}"))
    builder.row(InlineKeyboardButton(text="⛽ Benzinni o'zgartirish", callback_data=f"adm_change_fuel:{shift_id}"))
    # НОВАЯ КНОПКА:
    builder.row(InlineKeyboardButton(text="🛠 Boshqa xarajatni o'zgartirish", callback_data=f"adm_change_other:{shift_id}"))
    builder.row(InlineKeyboardButton(text="🏁 Tuzatishlarni yakunlash", callback_data=f"adm_finish_edit:{shift_id}"))
    builder.adjust(1)
    return builder.as_markup()


# 2. НОВАЯ: Петля внутри садика для админа (аналог водительской)
def get_admin_kg_loop_kb(shift_id: int):
    builder = InlineKeyboardBuilder()
    # Добавить еще товар в Тот же садик (стейт kindergarten_id сохранится)
    builder.button(text="➕ Yana mahsulot qo'shish", callback_data=f"adm_more_prod_same_kg:{shift_id}")
    # Завершить этот садик и вернуться в ГЛАВНОЕ меню правки
    builder.button(text="✅ Ushbu bog'chani yakunlash", callback_data=f"adm_finish_this_kg:{shift_id}")

    builder.adjust(1)
    return builder.as_markup()


# --- АНАЛИТИКА: ВЫБОР ПЕРИОДА ---
def get_analytics_period_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🕒 Bugun uchun", callback_data="adm_stats_period:today")
    builder.button(text="🕒 Kecha uchun", callback_data="adm_stats_period:yesterday")
    builder.button(text="📅 Shu oy uchun", callback_data="adm_stats_period:month")

    # Кнопки, которые сделаем позже на следующих этапах
    builder.button(text="🗓 Ixtiyoriy davr", callback_data="adm_stats_period:custom")
    builder.button(text="📥 Umumiy Excel", callback_data="adm_stats_export_all:xlsx")
    builder.button(text="📕 Umumiy PDF", callback_data="adm_stats_export_all:pdf")

    # Замени "admin_main" на тот callback, который у тебя ведет в главное меню админки
    builder.button(text="⬅️ Admin panelga qaytish", callback_data="admin_exit")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


# --- АНАЛИТИКА: ДАШБОРД (МЕНЮ ВНУТРИ ПЕРИОДА) ---
def get_dashboard_kb(period: str):
    builder = InlineKeyboardBuilder()

    # Детализация остается только для месячного отчета
    if period == "month":
        builder.button(text="👥 Haydovchilar bo'yicha tahlil", callback_data=f"adm_stats_drivers:{period}")

    builder.button(text="📗 Excel yuklab olish", callback_data=f"adm_stats_dl_xlsx:{period}")
    builder.button(text="📕 PDF yuklab olish", callback_data=f"adm_stats_dl_pdf:{period}")
    builder.button(text="⬅️ Davr tanlashga qaytish", callback_data="admin_stats")
    builder.adjust(1)
    return builder.as_markup()


def get_drivers_stats_kb(drivers_data, period: str, page: int = 0):
    builder = InlineKeyboardBuilder()
    limit = 6
    start = page * limit
    end = start + limit

    # Иконки для топ-3
    medals = ["🥇", "🥈", "🥉"]

    for i, d in enumerate(drivers_data[start:end]):
        rank = medals[i + start] if (i + start) < 3 else "👤"
        builder.button(
            text=f"{rank} {d['name']}: +{int(d['profit']):,} сум",
            callback_data=f"adm_stats_dr_view:{d['id']}:{period}"  # Если захотим детальный отчет по одному
        )

    builder.adjust(1)

    # Навигация (если водителей много)
    if len(drivers_data) > limit:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"adm_stats_drivers:{period}:{page - 1}"))
        if end < len(drivers_data):
            nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"adm_stats_drivers:{period}:{page + 1}"))
        if nav_row:
            builder.row(*nav_row)

    builder.row(InlineKeyboardButton(text="⬅️ Natijalarga qaytish", callback_data=f"adm_stats_period:{period}"))
    # ⬅️ Назад к итогам
    return builder.as_markup()