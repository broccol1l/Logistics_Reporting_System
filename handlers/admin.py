import os
from datetime import datetime, timedelta
from fpdf import FPDF
from aiogram.dispatcher.event.bases import SkipHandler

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload
from aiogram.types import Message
import pandas as pd
from io import BytesIO
from aiogram.types import FSInputFile, BufferedInputFile
from database.requests import (get_user_shifts, update_shift_date, get_user, delete_shift_full,
                               get_shift_by_id, get_shift_deliveries, unclose_shift,
                               delete_kg_from_active_shift, get_dashboard_stats,
                               get_drivers_performance, get_all_deliveries_for_export,
                               get_deliveries_by_period)

from database.models import User, Product, Kindergarten, Shift, Delivery
from utils.states import AdminState, AdminEdit, KGState, DeliveryState, AdminStatsState
from keyboards.inline import (admin_main_kb, get_products_list_kb, get_product_card_kb,
                              get_cancel_kb, get_units_kb, get_kg_list_kb,
                              get_kg_card_kb, get_user_card_kb, get_users_list_kb,
                              get_admin_user_history_kb, get_admin_report_tools_kb,
                              get_admin_edit_menu_kb, get_admin_manage_kgs_kb,
                              get_admin_edit_loop_kb, get_kg_paging_kb, get_products_paging_kb,
                              get_analytics_period_kb, get_dashboard_kb, get_drivers_stats_kb)

from keyboards.reply import main_menu_kb

router = Router()


# --- ВХОД В АДМИНКУ ---

@router.message(F.text == "⚙️ Admin paneli") # ⚙️ Админ-панель
@router.message(Command("admin"))
async def admin_mode_entry(message: types.Message, session: AsyncSession):
    result = await session.execute(select(User).where(User.id == message.from_user.id))
    user = result.scalar_one_or_none()

    if user and user.is_admin:
        await message.answer(
            "🛡 **Boshqaruv paneli (Admin Mode)**\nKerakli bo'limni tanlang:",
            reply_markup=admin_main_kb(),  # Главное Inline-меню
            parse_mode="Markdown"
        )
        # "🛡 **Панель управления (Admin Mode)**\nВыберите нужный раздел:"
    else:
        await message.answer("❌ Ushbu bo'limga kirish huquqingiz yo'q.")
        # "❌ У вас нет прав доступа к этому разделу."


# --- ВЫХОД ИЗ АДМИНКИ ---

@router.callback_query(F.data == "admin_exit")
async def exit_admin_mode(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()

    await callback.message.edit_text("✅ Admin rejimidan chiqdingiz. Endi haydovchi menyusi mavjud.")
    await callback.message.answer(
        "🚚 Ishchi menyuga qaytdingiz:",
        reply_markup=main_menu_kb(is_admin=True)  # Показываем кнопку админки внизу
    )
    # 🚚 Вы вернулись в рабочее меню:
    await callback.answer()


# --- КНОПКА "В НАЧАЛО" (Универсальная) ---

@router.callback_query(F.data == "admin_home")
async def back_to_admin_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🛡 **Boshqaruv paneli (Admin Mode)**\nKerakli bo'limni tanlang:",
        reply_markup=admin_main_kb(),
        parse_mode="Markdown"
    )
    # "🛡 **Панель управления (Admin Mode)**\nВыберите нужный раздел:"
    await callback.answer()


# --- РАЗДЕЛ: ТОВАРЫ ---
@router.callback_query(F.data.startswith("adm_prod_view:"))
async def admin_product_view(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer()

    product_id = int(callback.data.split(":")[1])

    product = await session.get(Product, product_id)

    if not product:
        await callback.message.edit_text("❌ Mahsulot bazadan topilmadi.") # ❌ Товар не найден в базе.
        return

    text = (
        f"📦 **Mahsulot kartochkasi:**\n\n"
        f"📝 **Nomi:** {product.name}\n"
        f"📏 **O'lchov birligi:** {product.unit}\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"💰 **Bog'cha narxi:** {int(product.price_sadik)} сум\n"
        f"📉 **Sotib olish narxi:** {int(product.price_zakup)} сум\n"
        f"📈 **Marja:** {int(product.price_sadik - product.price_zakup)} сум\n"
    )
        # f"📦 **Карточка товара:**\n\n"
        # f"📝 **Название:** {product.name}\n"
        # f"📏 **Ед. измерения:** {product.unit}\n"
        # f"➖➖➖➖➖➖➖➖\n"
        # f"💰 **Цена садика:** {int(product.price_sadik)} сум\n"
        # f"📉 **Цена закупа:** {int(product.price_zakup)} сум\n"
        # f"📈 **Маржа:** {int(product.price_sadik - product.price_zakup)} сум\n"

    try:
        await callback.message.edit_text(
            text,
            reply_markup=get_product_card_kb(product_id),
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Ошибка при выводе карточки: {e}") # f"Ошибка при выводе карточки: {e}"


# --- ОТМЕНА РЕДАКТИРОВАНИЯ ---
@router.callback_query(F.data == "admin_cancel_edit")
async def cancel_editing(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product_id = data.get("edit_product_id")
    await state.clear()

    if product_id:
        # Если был ID товара, возвращаем в его карточку
        await admin_product_view(callback, None)  # Вызываем хендлер просмотра
    else:
        await back_to_admin_main(callback, state)
    await callback.answer("Amal bekor qilindi") # "Действие отменено"




# --- ДОБАВЛЕНИЕ ТОВАРА ---

@router.callback_query(F.data == "adm_prod_add")
async def admin_product_add_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.waiting_product_name)
    await callback.message.edit_text(
        "📝 **1-qadam: Nomi**\nMahsulot nomini kiriting (masalan: Smetana 20%):",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown"
    )
    # "📝 **Шаг 1: Название**\nВведите название товара (например: *Сметана 20%*):"
    await callback.answer()


# 1. Получаем название -> спрашиваем единицу измерения
@router.message(AdminState.waiting_product_name)
async def admin_product_add_name(message: types.Message, state: FSMContext):
    await state.update_data(new_name=message.text)
    await state.set_state(AdminState.waiting_product_unit)

    await message.answer(
        f"✅ Nomi: {message.text}\n\n**2-qadam:** O'lchov birligini tanlang:",
        reply_markup=get_units_kb(),
        parse_mode="Markdown"
    )
    # f"✅ Название: {message.text}\n\n**Шаг 2:** Выберите единицу измерения:"


@router.callback_query(F.data.startswith("unit_set:"))
async def admin_product_add_unit(callback: types.CallbackQuery, state: FSMContext):
    unit = callback.data.split(":")[1]
    await state.update_data(new_unit=unit)

    await state.set_state(AdminState.waiting_p_sadik_add)
    await callback.message.edit_text(
        f"✅ O'lchov birligi: {unit}\n\n**3-qadam:** **BOG'CHA NARXINI** kiriting (son):",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown"
    )
    # f"✅ Единица измерения: {unit}\n\n**Шаг 3:** Введите **ЦЕНУ САДИКА** (число):"
    await callback.answer()

@router.message(AdminState.waiting_p_sadik_add)
async def admin_product_add_p_sadik(message: types.Message, state: FSMContext):
    clean_text = message.text.replace(" ", "").replace(",", ".")

    if not clean_text.replace(".", "", 1).isdigit():
        await message.answer("❌ To'g'ri son kiriting (masalan: 100 000 yoki 105.5):", reply_markup=get_cancel_kb())
        # "❌ Введите корректное число (например: 100 000 или 105.5):"
        return

    await state.update_data(new_p_sadik=float(clean_text))  # Используем clean_text!
    await state.set_state(AdminState.waiting_p_zakup_add)
    await message.answer("💰 **4-qadam:** **SOTIB OLISH NARXINI** kiriting (son):", reply_markup=get_cancel_kb())
    #"💰 **Шаг 4:** Введите **ЦЕНУ ЗАКУПА** (число):"



@router.message(AdminState.waiting_p_zakup_add)
async def admin_product_add_finish(message: types.Message, state: FSMContext, session: AsyncSession):
    clean_text = message.text.replace(" ", "").replace(",", ".")

    if not clean_text.replace(".", "", 1).isdigit():
        await message.answer("❌ Son kiriting!", reply_markup=get_cancel_kb())
        # "❌ Введите число!"
        return

    data = await state.get_data()
    p_zakup = float(clean_text)

    new_product = Product(
        name=data['new_name'],
        unit=data['new_unit'],
        price_sadik=data['new_p_sadik'],
        price_zakup=p_zakup,
        is_active=True
    )

    session.add(new_product)
    await session.commit()
    await state.clear()

    await message.answer(
        f"🎉 **Mahsulot muvaffaqiyatli qo'shildi!**\n\n"
        f"📦 {new_product.name}\n"
        f"📏 O'lchov birligi: {new_product.unit}\n"
        f"💰 Bog'cha narxi: {int(new_product.price_sadik)} сум\n"
        f"📉 Sotib olish narxi: {int(new_product.price_zakup)} сум",
        reply_markup=admin_main_kb(),
        parse_mode="Markdown"
    )
        # f"🎉 **Товар успешно добавлен!**\n\n"
        # f"📦 {new_product.name}\n"
        # f"📏 Ед. изм.: {new_product.unit}\n"
        # f"💰 Цена садика: {int(new_product.price_sadik)} сум\n"
        # f"📉 Цена закупа: {int(new_product.price_zakup)} сум"

@router.callback_query(F.data.startswith("adm_prod_delete:"))
async def delete_product(callback: types.CallbackQuery, session: AsyncSession):
    product_id = int(callback.data.split(":")[1])
    product = await session.get(Product, product_id)

    if product:
        product.is_active = False  # Soft delete
        await session.commit()
        await callback.answer(f"🗑'{product.name}' mahsuloti o'chirildi") # f"🗑 Товар '{product.name}' удален"
        await admin_products_list(callback, session)

@router.callback_query(F.data == "admin_products")
@router.callback_query(F.data.startswith("adm_prod_page:"))
async def admin_products_list(callback: types.CallbackQuery, session: AsyncSession):
    page = 0
    if callback.data.startswith("adm_prod_page:"):
        page = int(callback.data.split(":")[1])

    result = await session.execute(select(Product).where(Product.is_active == True).order_by(Product.name))
    products = result.scalars().all()

    if not products:
        await callback.message.edit_text(
            "📦 Mahsulotlar ro'yxati bo'sh.",
            reply_markup=get_products_list_kb([], page)
        )
        # "📦 Список товаров пуст."
    else:
        await callback.message.edit_text(
            f"📦 **Mahsulotlar ro'yxati (Страница {page + 1})**\nTahrirlash uchun mahsulot ustiga bosing:",
            reply_markup=get_products_list_kb(products, page),
            parse_mode="Markdown"
        )
        # f"📦 **Список товаров (Страница {page + 1})**\nНажмите на товар для редактирования:"
    await callback.answer()


# --- РЕДАКТИРОВАНИЕ ЦЕНЫ (НАЧАЛО) ---

@router.callback_query(F.data.startswith("adm_prod_edit:"))
async def admin_product_edit_start(callback: types.CallbackQuery, state: FSMContext):
    _, field, product_id = callback.data.split(":")
    product_id = int(product_id)

    await state.update_data(edit_product_id=product_id, edit_field=field)

    if field == "p_sadik":
        # 💰 Введите новую **ЦЕНУ САДИКА**:
        await callback.message.answer("💰 Yangi BOG'CHA NARXINI kiriting:", reply_markup=get_cancel_kb())
        await state.set_state(AdminEdit.waiting_p_sadik_edit)
    elif field == "p_zakup":
        # 📉 Введите новую **ЦЕНУ ЗАКУПА**:
        await callback.message.answer("📉 Yangi SOTIB OLISH NARXINI kiriting:", reply_markup=get_cancel_kb())
        await state.set_state(AdminEdit.waiting_p_zakup_edit)
    elif field == "name":
        # ✏️ Введите новое **НАЗВАНИЕ** товара:
        await callback.message.answer("✏️ Mahsulotning yangi NOMINI kiriting:", reply_markup=get_cancel_kb())
        await state.set_state(AdminEdit.waiting_name_edit) # Убедись, что этот стейт есть в states.py
    # ---------------------------------

    await callback.answer()


# --- СОХРАНЕНИЕ ЦЕНЫ ---
# --- ЕДИНАЯ ФУНКЦИЯ СОХРАНЕНИЯ ПРИ РЕДАКТИРОВАНИИ ---
@router.message(AdminEdit.waiting_p_sadik_edit)
@router.message(AdminEdit.waiting_p_zakup_edit)
async def save_edited_price(message: Message, state: FSMContext, session: AsyncSession):
    clean_text = message.text.replace(" ", "").replace(",", ".")

    if not clean_text.replace(".", "", 1).isdigit():
        await message.answer("❌ Xato! To'g'ri son kiriting (masalan: 105000):", reply_markup=get_cancel_kb())
        return

    new_price = float(clean_text)

    data = await state.get_data()
    product_id = data.get("edit_product_id")
    field = data.get("edit_field")

    product = await session.get(Product, product_id)
    if not product:
        await message.answer("❌ Xatolik: mahsulot topilmadi.")
        await state.clear()
        return

    if field == "p_sadik":
        product.price_sadik = new_price
    else:
        product.price_zakup = new_price

    await session.commit()
    await state.clear()  # Очищаем FSM

    text = (
        f"✅ **{product.name}** mahsuloti narxi muvaffaqiyatli yangilandi!\n\n"
        f"💰 Bog'cha narxi: {int(product.price_sadik)} so'm\n"
        f"📉 Sotib olish narxi: {int(product.price_zakup)} so'm\n"
        f"📈 Marja: {int(product.price_sadik - product.price_zakup)} so'm"
    )
      # f"✅ Цена товара **{product.name}** успешно обновлена!\n\n"
      # f"💰 Цена садика: {int(product.price_sadik)} сум\n"
      # f"📉 Цена закупа: {int(product.price_zakup)} сум\n"
      # f"📈 Маржа: {int(product.price_sadik - product.price_zakup)} сум"

    await message.answer(
        text,
        reply_markup=get_product_card_kb(product.id),
        parse_mode="Markdown"
    )


@router.message(AdminEdit.waiting_name_edit)
async def save_edited_name(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    product_id = data.get("edit_product_id")

    product = await session.get(Product, product_id)
    if product:
        old_name = product.name
        product.name = message.text
        await session.commit()
        await state.clear()

        await message.answer(
            f"✅ Nomi o'zgartirildi!\nEski nomi: {old_name}\nYangi nomi: **{product.name}**",
            reply_markup=get_product_card_kb(product.id),
            parse_mode="Markdown"
        )
        # f"✅ Название изменено!\nБыло: {old_name}\nСтало: **{product.name}**"


# --- РАЗДЕЛ: САДИКИ ---

@router.callback_query(F.data == "admin_kindergartens")
@router.callback_query(F.data.startswith("adm_kg_page:"))
async def admin_kg_list(callback: types.CallbackQuery, session: AsyncSession):
    page = int(callback.data.split(":")[1]) if ":" in callback.data else 0

    result = await session.execute(
        select(Kindergarten).where(Kindergarten.is_active == True).order_by(Kindergarten.name))
    kg_list = list(result.scalars().all())

    await callback.message.edit_text(
        f"🏫 **Bog'chalar ro'yxati ({page + 1}-sahifa)**:",
        reply_markup=get_kg_list_kb(kg_list, page),
        parse_mode="Markdown"
    )
    # f"🏫 **Список садиков (Страница {page + 1})**:"
    await callback.answer()


@router.callback_query(F.data.startswith("adm_kg_view:"))
async def admin_kg_view(callback: types.CallbackQuery, session: AsyncSession):
    kg_id = int(callback.data.split(":")[1])
    kg = await session.get(Kindergarten, kg_id)

    if not kg:
        await callback.answer("❌ Bog'cha topilmadi")
        # "❌ Садик не найден"
        return

    await callback.message.edit_text(
        f"🏫 **Obyekt:** {kg.name}\n\nBu yerda nomni o'zgartirish yoki obyektni faol ro'yxatdan o'chirish mumkin.",
        reply_markup=get_kg_card_kb(kg_id),
        parse_mode="Markdown"
    )
    # f"🏫 **Объект:** {kg.name}\n\nЗдесь можно изменить название или удалить объект из активного списка."
    await callback.answer()


# --- РАЗДЕЛ: САДИКИ ---

@router.callback_query(F.data == "admin_kindergartens")
@router.callback_query(F.data.startswith("adm_kg_page:"))
async def admin_kg_list(callback: types.CallbackQuery, session: AsyncSession):
    if callback.data.startswith("adm_kg_page:"):
        page = int(callback.data.split(":")[1])
    else:
        page = 0

    result = await session.execute(
        select(Kindergarten).where(Kindergarten.is_active == True).order_by(Kindergarten.name)
    )
    kg_list = list(result.scalars().all())

    limit = 6
    if page > 0 and len(kg_list) <= page * limit:
        page -= 1

    await callback.message.edit_text(
        f"🏫 **Bog'chalar ro'yxati ({page + 1}-sahifa)**:",
        reply_markup=get_kg_list_kb(kg_list, page),
        parse_mode="Markdown"
    )
    # f"🏫 **Список садиков (Страница {page + 1})**:"
    await callback.answer()


@router.callback_query(F.data.startswith("adm_kg_view:"))
async def admin_kg_view(callback: types.CallbackQuery, session: AsyncSession):
    kg_id = int(callback.data.split(":")[1])
    kg = await session.get(Kindergarten, kg_id)

    if not kg:
        await callback.answer("❌ Bog'cha topilmadi")
        return

    await callback.message.edit_text(
        f"🏫 **Obyekt:** {kg.name}\n\nBu yerda nomni o'zgartirish yoki obyektni faol ro'yxatdan o'chirish mumkin",
        reply_markup=get_kg_card_kb(kg_id),
        parse_mode="Markdown"
    )
    # f"🏫 **Объект:** {kg.name}\n\nЗдесь можно изменить название или удалить объект из активного списка."
    await callback.answer()


# --- ДОБАВЛЕНИЕ САДИКА ---

@router.callback_query(F.data == "adm_kg_add")
async def admin_kg_add_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(KGState.waiting_kg_name)  # Используем твой стейт
    await callback.message.edit_text(
        "📝 Yangi bog'cha nomini kiriting (masalan: 52-sonli bog'cha):",
        reply_markup=get_cancel_kb(),
        parse_mode="Markdown"
    )
    # "📝 Введите название нового садика (например: *Садик №52*):"
    await callback.answer()


@router.message(KGState.waiting_kg_name)
async def admin_kg_add_finish(message: types.Message, state: FSMContext, session: AsyncSession):
    new_kg = Kindergarten(name=message.text, is_active=True)
    session.add(new_kg)

    try:
        await session.commit()
        await state.clear()
        # f"✅ Садик **{new_kg.name}** успешно добавлен!"
        await message.answer(f"✅ **{new_kg.name}** bog'chasi muvaffaqiyatli qo'shildi!", reply_markup=admin_main_kb())
    except Exception:
        await session.rollback()
        # "❌ Ошибка: садик с таким названием уже существует."
        await message.answer("❌ Xatolik: bunday nomli bog'cha allaqachon mavjud.")


@router.callback_query(F.data.startswith("adm_kg_delete:"))
async def admin_kg_delete(callback: types.CallbackQuery, session: AsyncSession):
    kg_id = int(callback.data.split(":")[1])
    kg = await session.get(Kindergarten, kg_id)

    if kg:
        kg.is_active = False  # Просто скрываем
        await session.commit()
        await callback.answer(f"🗑 {kg.name} o'chirildi")
        # f"🗑 {kg.name} удален"
        await admin_kg_list(callback, session)  # Возвращаемся к списку


@router.callback_query(F.data.startswith("adm_kg_edit:"))
async def admin_kg_edit_start(callback: types.CallbackQuery, state: FSMContext):
    kg_id = int(callback.data.split(":")[1])

    await state.update_data(edit_kg_id=kg_id)
    await state.set_state(KGState.waiting_kg_edit_name)

    await callback.message.answer(
        "✏️ Ushbu bog'cha uchun yangi nom kiriting:",
        reply_markup=get_cancel_kb()  # Используем нашу кнопку отмены
    )
    # "✏️ Введите **новое название** для этого садика:"
    await callback.answer()


@router.message(KGState.waiting_kg_edit_name)
async def admin_kg_edit_save(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    kg_id = data.get("edit_kg_id")

    kg = await session.get(Kindergarten, kg_id)

    if not kg:
        await message.answer("❌ Xatolik: bog'cha topilmadi.")
        # "❌ Ошибка: садик не найден."
        await state.clear()
        return

    old_name = kg.name
    kg.name = message.text

    await session.commit()
    await state.clear()

    await message.answer(
        f"✅ Nomi muvaffaqiyatli o'zgartirildi!\n\n"
        f"Было: *{old_name}*\n"
        f"Стало: **{kg.name}**",
        reply_markup=get_kg_card_kb(kg.id),
        parse_mode="Markdown"
    )
    # f"✅ Название успешно изменено!\n\n"
    #         f"Eski nomi: *{old_name}*\n"
    #         f"Yangi nomi: **{kg.name}**",


# --- РАЗДЕЛ: ПОЛЬЗОВАТЕЛИ ---

@router.callback_query(F.data == "admin_drivers")
@router.callback_query(F.data.startswith("adm_user_page:"))
async def admin_users_list(callback: types.CallbackQuery, session: AsyncSession):
    page = int(callback.data.split(":")[1]) if ":" in callback.data else 0

    result = await session.execute(
        select(User)
        .where(User.is_visible_in_admin == True)
        .order_by(User.full_name)
    )
    users = list(result.scalars().all())

    await callback.message.edit_text(
        f"👥 **Foydalanuvchilarni boshqarish ({page + 1}-sahifa)**\n\n"
        f"🛡️ — Admin\n🚚 — Haydovchi\n🚫 — Bloklangan",
        reply_markup=get_users_list_kb(users, page),
        parse_mode="Markdown"
    )
    # f"👥 **Управление пользователями (Стр. {page + 1})**\n\n"
    #         f"🛡️ — Админ\n🚚 — Водитель\n🚫 — Заблокирован"
    await callback.answer()


@router.callback_query(F.data.startswith("adm_user_view:"))
async def admin_user_view(callback: types.CallbackQuery, session: AsyncSession):
    user_id = int(callback.data.split(":")[-1])

    user = await session.get(User, user_id)

    if not user:
        await callback.message.edit_text("❌ Пользователь не найден в базе.") # "❌ Пользователь не найден в базе."
        return

    role = "Administrator 🛡️" if user.is_admin else "Haydovchi 🚚"  # "Администратор 🛡️" if user.is_admin else "Водитель 🚚"
    status = "Bloklangan 🚫" if user.is_blocked else "Faol ✅" # "Заблокирован 🚫" if user.is_blocked else "Работает ✅"

    text = (
        f"👤 **Foydalanuvchi kartochkasi**\n\n"
        f"🆔 ID: `{user.id}`\n"
        f"📝 Ism: {user.full_name or 'Ko\'rsatilmagan'}\n"
        f"📞 Tel: {user.phone or 'Bog\'lanmagan'}\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"🎭 Rol: {role}\n"
        f"📊 Status: {status}"
    )
      # f"👤 **Карточка пользователя**\n\n"
      # f"🆔 ID: `{user.id}`\n"
      # f"📝 Имя: {user.full_name or 'Не указано'}\n"
      # f"📞 Тел: {user.phone or 'Не привязан'}\n"
      # f"➖➖➖➖➖➖➖➖\n"
      # f"🎭 Роль: {role}\n"
      # f"📊 Статус: {status}"

    await callback.message.edit_text(
        text,
        reply_markup=get_user_card_kb(user_id, user.is_admin, user.is_blocked),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_user_set:"))
async def admin_user_set_role(callback: types.CallbackQuery, session: AsyncSession):
    _, action, user_id = callback.data.split(":")
    user_id = int(user_id)

    if user_id == callback.from_user.id:
        await callback.answer("❌ O'z huquqlaringizni o'zgartira olmaysiz!", show_alert=True) # "❌ Нельзя менять права самому себе!"
        return

    user = await session.get(User, user_id)
    if not user:
        await callback.answer("Foydalanuvchi topilmadi")
        return

    if action == "promote":
        user.is_admin = True
    elif action == "demote":
        user.is_admin = False
    elif action == "block":
        user.is_blocked = True
        user.is_admin = False
    elif action == "unblock":
        user.is_blocked = False

    await session.commit()
    await session.refresh(user)

    await callback.answer(f"✅ Status yangilandi") # ✅ Статус обновлен"

    await admin_user_view(callback, session)



@router.callback_query(F.data.startswith("adm_history:"))
@router.callback_query(F.data.startswith("adm_rep_page:"))
async def admin_show_user_history(callback: types.CallbackQuery, session: AsyncSession, user_id_override: int = None):
    if user_id_override:
        user_id = user_id_override
        page = 0
    else:
        parts = callback.data.split(":")
        user_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 0

    limit = 5
    offset = page * limit
    shifts = await get_user_shifts(session, user_id, limit, offset)

    if not shifts and page == 0:
        await callback.message.edit_text(
            "Ushbu haydovchida boshqa hisobotlar yo'q.",
            reply_markup=get_user_card_kb(user_id, False, False)
        )
        return

    await callback.message.edit_text(
        f"📂 **Hisobotlar tarixi ({page + 1}-sahifa)**",
        reply_markup=get_admin_user_history_kb(shifts, user_id, page),
        parse_mode="Markdown"
    )
    # f"📂 **История отчетов (стр. {page + 1})**"



@router.callback_query(F.data.startswith("adm_view_rep:"))
async def admin_view_single_report(callback: types.CallbackQuery, session: AsyncSession, shift_id_override: int = None):
    if shift_id_override:
        shift_id = shift_id_override
    else:
        shift_id = int(callback.data.split(":")[1])

    result_shift = await session.execute(
        select(Shift).where(Shift.id == shift_id).options(selectinload(Shift.driver))
    )
    shift = result_shift.scalar_one_or_none()

    result_deliveries = await session.execute(
        select(Delivery).where(Delivery.shift_id == shift_id).options(
            selectinload(Delivery.product),
            selectinload(Delivery.kindergarten)
        )
    )
    deliveries = result_deliveries.scalars().all()

    if not shift:
        await callback.answer("⚠️ Smena topilmadi.", show_alert=True)  # "⚠️ Смена не найдена."
        return

    report_text = f"📋 **{shift.opened_at.strftime('%d.%m.%Y')} sana uchun batafsil hisobot**\n"
    report_text += f"👤 Haydovchi: {shift.driver.full_name if shift.driver else 'O\'chirilgan'}\n"
    report_text += "───────────────────\n"

    total_sum = 0
    total_cost = 0

    if not deliveries:
        report_text += "_Yetkazib berishlar qayd etilmadi_\n"  # "_Отгрузок не зафиксировано_\n"
    else:
        for d in deliveries:
            report_text += f"🏫 {d.kindergarten.name}\n"
            report_text += f"  ◦ {d.product.name}: {d.weight_fact} {d.product.unit} = {int(d.total_price_sadik):,} so'm\n"
            total_sum += d.total_price_sadik
            total_cost += d.total_cost_zakup

    # --- НОВЫЕ РАСХОДЫ ---
    fuel = shift.fuel_expense or 0
    other_exp = shift.other_expenses or 0
    other_comment = shift.other_expenses_comment or ""

    total_expenses = fuel + other_exp
    final_amount = total_sum - total_expenses
    net_profit = total_sum - total_cost - total_expenses

    report_text += "───────────────────\n"
    report_text += f"💰 UMUMIY TUSHUM: **{int(total_sum):,} so'm**\n"
    report_text += f"⛽ Benzin: **-{int(fuel):,} so'm**\n"

    if other_exp > 0:
        comment_str = f" ({other_comment})" if other_comment else ""
        report_text += f"🛠 Boshqa xarajatlar: **-{int(other_exp):,} so'm**{comment_str}\n"

    report_text += "───────────────────\n"
    report_text += f"💵 **KASSA (HAYDOVCHI TOPSHIRADI): {int(final_amount):,} so'm**\n"
    report_text += f"📈 **SOF FOYDA: {int(net_profit):,} so'm**"

    from keyboards.inline import get_admin_report_tools_kb
    await callback.message.edit_text(
        report_text,
        reply_markup=get_admin_report_tools_kb(shift.id, shift.user_id),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_del_rep:"))
async def admin_delete_report(callback: types.CallbackQuery, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])

    shift = await session.get(Shift, shift_id)
    if not shift:
        await callback.answer("Hisobot allaqachon o'chirildi.") # "Отчет уже удален."
        return

    user_id = shift.user_id

    await delete_shift_full(session, shift_id)
    await callback.answer("🚨 Hisobot butunlay o'chirildi!", show_alert=True) # "🚨 Отчет полностью удален!"

    await admin_show_user_history(callback, session, user_id_override=user_id)



@router.callback_query(F.data.startswith("adm_edit_rep:"))
async def admin_edit_report_start(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])

    await unclose_shift(session, shift_id)
    await state.clear()
    await state.update_data(shift_id=shift_id)

    await callback.message.edit_text(
        "🛠 **TAHRIRLASH REJIMI (ADMIN)**\nNima qilishni xohlaysiz?",
        reply_markup=get_admin_edit_loop_kb(shift_id),
        parse_mode="Markdown"
    )
    # 🛠 **РЕЖИМ РЕДАКТИРОВАНИЯ (АДМИН)**\nЧто вы хотите сделать?


@router.callback_query(F.data.startswith("adm_add_kg_start:"))
async def admin_add_kg_start(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])
    await state.update_data(shift_id=shift_id)

    from database.requests import get_active_kindergartens
    kgs = await get_active_kindergartens(session)

    await state.set_state(DeliveryState.object_name)

    await callback.message.edit_text(
        "🏫 **Hisobotga bog'cha qo'shish**\nObyektni tanlang:",
        reply_markup=get_kg_paging_kb(kgs, page=0),
        parse_mode="Markdown"
    )
    # 🏫 **Добавление садика в отчет**\nВыберите объект:
    await callback.answer()

@router.callback_query(F.data.startswith("adm_manage_shift:"))
async def admin_manage_shift_kgs(callback: types.CallbackQuery, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])
    deliveries = await get_shift_deliveries(session, shift_id)

    if not deliveries:
        await callback.answer("Ushbu smena bo'sh.", show_alert=True)
        return

    kgs = {d.kindergarten.id: d.kindergarten.name for d in deliveries}

    await callback.message.edit_text(
        "🔍 **Bog'chalarni boshqarish:**\nHisobotdan BUTUNLAY o'chirish uchun bog'chani tanlang:",
        reply_markup=get_admin_manage_kgs_kb(kgs, shift_id)
    )
    # 🔍 **Управление садиками:**\nВыберите садик для ПОЛНОГО удаления из отчета:

@router.callback_query(F.data.startswith("adm_del_kg:"))
async def admin_delete_kg_from_shift(callback: types.CallbackQuery, session: AsyncSession):
    data_parts = callback.data.split(":")
    shift_id = int(data_parts[1])
    kg_id = int(data_parts[2])

    await delete_kg_from_active_shift(session, shift_id, kg_id)
    await callback.answer("✅ Bog'cha o'chirildi", show_alert=True)
    # ✅ Садик удален
    await admin_manage_shift_kgs(callback, session)


@router.callback_query(F.data.startswith("adm_finish_edit:"))
async def admin_finish_edit(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])

    await session.execute(
        update(Shift).where(Shift.id == shift_id).values(is_closed=True)
    )
    await session.commit()
    await state.clear()

    await callback.answer("✅ Tuzatishlar saqlandi")
    # ✅ Правки сохранены

    await admin_view_single_report(callback, session, shift_id_override=shift_id)


@router.callback_query(F.data.startswith("adm_more_prod_same_kg:"))
async def admin_add_more_product_same_kg(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    from database.requests import get_all_products
    products = await get_all_products(session)

    await state.set_state(DeliveryState.choosing_product)
    await callback.message.edit_text(
        "Ushbu bog'cha uchun keyingi mahsulotni tanlang:",
        reply_markup=get_products_paging_kb(products, page=0)
    )
    # Выберите следующий товар для этого садика:

@router.callback_query(F.data.startswith("adm_finish_this_kg:"))
async def admin_finish_kg_and_return(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])

    await callback.message.edit_text(
        "✅ Bog'cha yozib olindi. Keyingi qadam nima?",
        reply_markup=get_admin_edit_loop_kb(shift_id)
    )
    # ✅ Садик записан. Что делаем дальше?

@router.callback_query(F.data == "finish_this_kg")
async def intercept_finish_kg(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_user(session, callback.from_user.id)

    if not user.is_admin:
        raise SkipHandler()

    data = await state.get_data()
    shift_id = data.get("shift_id")
    await callback.message.edit_text("Bog'cha yakunlandi. Tahrirlash menyusiga qaytilmoqda...",
                                     reply_markup=get_admin_edit_loop_kb(shift_id))
    # Садик завершен. Возвращаюсь в меню правки...

@router.callback_query(F.data == "go_to_close_shift")
async def intercept_close_shift(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    user = await get_user(session, callback.from_user.id)

    if not user.is_admin:
        raise SkipHandler()

    data = await state.get_data()
    shift_id = data.get("shift_id")

    await session.execute(update(Shift).where(Shift.id == shift_id).values(is_closed=True))
    await session.commit()
    await state.clear()

    await callback.answer("✅ Tuzatishlar saqlandi")
    # ✅ Правки сохранены
    await admin_view_single_report(callback, session, shift_id_override=shift_id)


@router.callback_query(F.data.startswith("adm_change_date:"))
async def admin_change_date_request(callback: types.CallbackQuery):
    shift_id = int(callback.data.split(":")[1])

    builder = InlineKeyboardBuilder()
    today = datetime.now().strftime("%d.%m")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%d.%m")

    builder.button(text=f"📅 Bugun ({today})", callback_data=f"adm_apply_date:today:{shift_id}")
    builder.button(text=f"📅 Kecha ({yesterday})", callback_data=f"adm_apply_date:yesterday:{shift_id}")
    builder.button(text="⬅️ Ortga", callback_data=f"adm_edit_rep:{shift_id}")  # Возврат в меню правки
    builder.adjust(1)

    await callback.message.edit_text(
        "Ushbu smena uchun yangi sanani tanlang:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    # Выберите новую дату для этой смены:


@router.callback_query(F.data.startswith("adm_apply_date:"))
async def admin_apply_date_fix(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    parts = callback.data.split(":")
    date_type = parts[1]
    shift_id = int(parts[2])

    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    new_date = now if date_type == "today" else now - timedelta(days=1)

    await update_shift_date(session, shift_id, new_date)
    await callback.answer(f"📅 Sana {new_date.strftime('%d.%m')} га ўзгартирилди", show_alert=True)
    # 📅 Дата изменена на ...
    await callback.message.edit_text(
        f"✅ Sana **{new_date.strftime('%d.%m.%Y')}** га ўзгартирилди.\n\nKeyingi qadam nima?",
        reply_markup=get_admin_edit_loop_kb(shift_id),
        parse_mode="Markdown"
    )
    # ✅ Дата изменена на ... Что делаем дальше?

@router.callback_query(F.data.startswith("adm_change_fuel:"))
async def admin_change_fuel_start(callback: types.CallbackQuery, state: FSMContext):
    shift_id = int(callback.data.split(":")[1])

    await state.update_data(shift_id=shift_id)
    await state.set_state(AdminEdit.waiting_shift_fuel)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Bekor qilish", callback_data=f"adm_edit_rep:{shift_id}")
    # ❌ Отмена
    await callback.message.edit_text(
        "⛽ **Benzin xarajatini o'zgartirish**\n\nYangi summani raqamlarda kiriting (masalan: `50000`):",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.message(AdminEdit.waiting_shift_fuel)
async def admin_change_fuel_process(message: types.Message, state: FSMContext, session: AsyncSession):
    try:
        clean_text = message.text.replace('.', '').replace(',', '')
        new_fuel = float(clean_text)
    except ValueError:
        await message.answer("⚠️ Xato! Summani faqat raqamlarda kiriting.")
        # ⚠️ Ошибка! Введите сумму только цифрами.
        return

    data = await state.get_data()
    shift_id = data.get("shift_id")

    await session.execute(
        update(Shift).where(Shift.id == shift_id).values(fuel_expense=new_fuel)
    )
    await session.commit()

    await state.set_state(None)

    from keyboards.inline import get_admin_edit_loop_kb
    await message.answer(
        f"✅ Benzin xarajati **{int(new_fuel):,} so'm**ga yangilandi.\n\nKeyingi qadam nima?",
        reply_markup=get_admin_edit_loop_kb(shift_id),
        parse_mode="Markdown"
    )
    # LAST SAVE {new_fuel:,}
    # ✅ Расход на бензин обновлен на... Что делаем дальше?

# --- РЕДАКТИРОВАНИЕ ПРОЧИХ РАСХОДОВ ---

@router.callback_query(F.data.startswith("adm_change_other:"))
async def admin_change_other_start(callback: types.CallbackQuery, state: FSMContext):
    shift_id = int(callback.data.split(":")[1])

    await state.update_data(shift_id=shift_id)
    await state.set_state(AdminEdit.waiting_shift_other_exp)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Bekor qilish", callback_data=f"adm_edit_rep:{shift_id}")

    await callback.message.edit_text(
        "🛠 **Boshqa xarajatlarni o'zgartirish**\n\nYangi summani raqamlarda kiriting.\nAgar xarajatni o'chirmoqchi bo'lsangiz, `0` yozing:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.message(AdminEdit.waiting_shift_other_exp)
async def admin_change_other_amount(message: types.Message, state: FSMContext, session: AsyncSession):
    try:
        clean_text = message.text.replace('.', '').replace(',', '').replace(' ', '')
        amount = float(clean_text)
    except ValueError:
        await message.answer("⚠️ Xato! Summani faqat raqamlarda kiriting.")
        return

    data = await state.get_data()
    shift_id = data.get("shift_id")
    from keyboards.inline import get_admin_edit_loop_kb

    if amount == 0:
        await session.execute(
            update(Shift).where(Shift.id == shift_id).values(
                other_expenses=0.0,
                other_expenses_comment=""
            )
        )
        await session.commit()
        await state.set_state(None)

        await message.answer(
            "✅ Boshqa xarajatlar o'chirildi (0 so'm).\n\nKeyingi qadam nima?",
            reply_markup=get_admin_edit_loop_kb(shift_id),
            parse_mode="Markdown"
        )
        return

    await state.update_data(new_other_amount=amount)
    await state.set_state(AdminEdit.waiting_shift_other_comment)

    await message.answer("📝 Ushbu xarajat nima uchun qilinganini yozing (masalan: obed, remont, jarima):")


@router.message(AdminEdit.waiting_shift_other_comment)
async def admin_change_other_comment(message: types.Message, state: FSMContext, session: AsyncSession):
    comment = message.text
    data = await state.get_data()
    shift_id = data.get("shift_id")
    amount = data.get("new_other_amount")

    await session.execute(
        update(Shift).where(Shift.id == shift_id).values(
            other_expenses=amount,
            other_expenses_comment=comment
        )
    )
    await session.commit()

    await state.set_state(None)

    from keyboards.inline import get_admin_edit_loop_kb
    await message.answer(
        f"✅ Boshqa xarajatlar yangilandi: **{int(amount):,} so'm** ({comment})\n\nKeyingi qadam nima?",
        reply_markup=get_admin_edit_loop_kb(shift_id),
        parse_mode="Markdown"
    )

# АНАЛИТИКА
@router.callback_query(F.data == "admin_stats")
async def admin_stats_main(callback: types.CallbackQuery, session: AsyncSession):


    users_count = await session.scalar(select(func.count(User.id)))
    products_count = await session.scalar(
        select(func.count(Product.id)).where(Product.is_active == True)  # НА СЕРВАК
    )
    kg_count = await session.scalar(
        select(func.count(Kindergarten.id)).where(Kindergarten.is_active == True)
    )

    text = (
        "📊 **BAZANING UMUMIY STATISTIKASI**\n\n"
        f"👥 Foydalanuvchilar: **{users_count}**\n"
        f"📦 Mahsulot turlari: **{products_count}**\n"
        f"🏫 Bog'chalar: **{kg_count}**\n"
        "───────────────────\n"
        "📈 **MOLIYAVIY ANALITIKA**\n"
        "Tushum va sof foydani hisoblash uchun davrni tanlang:"
    )
    # text = (
    #         "📊 **ОБЩАЯ СТАТИСТИКА БАЗЫ**\n\n"
    #         f"👥 Пользователей: **{users_count}**\n"
    #         f"📦 Видов товаров: **{products_count}**\n"
    #         f"🏫 Садиков: **{kg_count}**\n"
    #         "───────────────────\n"
    #         "📈 **ФИНАНСОВАЯ АНАЛИТИКА**\n"
    #         "Выберите период для расчета выручки и чистой прибыли:"
    #     )
    # 📊 **ОБЩАЯ СТАТИСТИКА БАЗЫ** ... Выберите период для расчета...
    await callback.message.edit_text(
        text,
        reply_markup=get_analytics_period_kb(),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("adm_stats_period:"))
async def admin_stats_dashboard(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    period = callback.data.split(":")[1]

    if period == "custom":
        await state.set_state(AdminStatsState.waiting_custom_period)

        builder = InlineKeyboardBuilder()
        builder.button(text="❌ Отмена", callback_data="admin_stats")

        await callback.message.edit_text(
            "🗓 **Ixtiyoriy davr tahlili**\n\n"
            "Ikki sanani chiziqcha orqali `KK.OO.YYYY - KK.OO.YYYY` formatida kiriting.\n\n"
            "Misol: `01.04.2026 - 15.04.2026`",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
        return

    now = datetime.now()

    if period == "today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        period_name = "BUGUN" # СЕГОДНЯ

    elif period == "yesterday":
        start_date = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        period_name = "KECHA" # ВЧЕРА

    elif period == "month":
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        months = ["YANVAR", "FEVRAL", "MART", "APREL", "MAY", "IYUN", "IYUL", "AVGUST", "SENTYABR", "OKTYABR",
                  "NOYABR", "DEKABR"]
        period_name = f"{months[now.month - 1]} {now.year}"

    elif "-" in period:
        start_str, end_str = period.split("-")
        start_date = datetime.strptime(start_str, "%Y%m%d").replace(hour=0, minute=0, second=0)
        end_date = datetime.strptime(end_str, "%Y%m%d").replace(hour=23, minute=59, second=59)
        period_name = f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"

    stats = await get_dashboard_stats(session, start_date, end_date)
    profitability = (stats["profit"] / stats["revenue"] * 100) if stats["revenue"] > 0 else 0

    # --- НОВЫЕ РАСХОДЫ ---
    text = (
        f"📊 **{period_name} UCHUN NATIJALAR**:\n\n"
        f"💰 Aylanma (Tushum): **{int(stats['revenue']):,} so'm**\n"
        f"📉 Mahsulot xarajatlari: **{int(stats['cost']):,} so'm**\n"
        f"⛽️ Benzin xarajatlari: **{int(stats['fuel']):,} so'm**\n"
    )

    if stats.get('other_exp', 0) > 0:
        text += f"🛠 Boshqa xarajatlar: **{int(stats['other_exp']):,} so'm**\n"

    text += (
        f"───────────────────\n"
        f"🏆 **SOF FOYDA: {int(stats['profit']):,} so'm**\n\n"
        f"📈 Biznes rentabelligi: **{profitability:.1f}%**"
    )

    from keyboards.inline import get_dashboard_kb
    await callback.message.edit_text(text, reply_markup=get_dashboard_kb(period), parse_mode="Markdown")

@router.callback_query(F.data.startswith("adm_stats_drivers:"))
async def admin_stats_drivers_list(callback: types.CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    period = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0

    now = datetime.now()
    if period == "today":
        start_date = now.replace(hour=0, minute=0, second=0)
        end_date = now.replace(hour=23, minute=59, second=59)
    elif period == "yesterday":
        start_date = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0)
        end_date = start_date.replace(hour=23, minute=59, second=59)
    elif period == "month":
        start_date = now.replace(day=1, hour=0, minute=0, second=0)
        end_date = now.replace(hour=23, minute=59, second=59)
    elif "-" in period:
        start_str, end_str = period.split("-")
        start_date = datetime.strptime(start_str, "%Y%m%d").replace(hour=0, minute=0, second=0)
        end_date = datetime.strptime(end_str, "%Y%m%d").replace(hour=23, minute=59, second=59)

    drivers_data = await get_drivers_performance(session, start_date, end_date)

    if not drivers_data:
        await callback.answer("Ushbu davr uchun haydovchilar bo'yicha ma'lumot topilmadi.", show_alert=True)
        return

    await callback.message.edit_text(
        f"👥 **Haydovchilar samaradorligi**\n"
        f"Davr: {period.upper()}\n"
        f"(Xarid, benzin va boshqa xarajatlar chegirilgandagi sof foyda)", # Добавлено "va boshqa xarajatlar"
        reply_markup=get_drivers_stats_kb(drivers_data, period, page),
        parse_mode="Markdown"
    )
    # f"👥 **Эффективность водителей**\n"
    #         f"Период: {period.upper()}\n"
    #         f"(Чистая прибыль после вычета закупа и бензина)",


@router.message(AdminStatsState.waiting_custom_period, F.text) # НА СЕРВАК
async def admin_process_custom_dates(message: types.Message, state: FSMContext, session: AsyncSession):
    text = message.text.strip()

    try:
        start_str, end_str = text.split("-")

        start_date = datetime.strptime(start_str.strip(), "%d.%m.%Y").replace(hour=0, minute=0, second=0)
        end_date = datetime.strptime(end_str.strip(), "%d.%m.%Y").replace(hour=23, minute=59, second=59)

        if start_date > end_date:
            raise ValueError("Boshlanish sanasi tugash sanasidan katta")

    except ValueError:
        await message.answer(
            "❌ **Format xatosi!**\nIltimos, sanalarni худди намунадагидек киритинг:\n`01.04.2026 - 15.04.2026`",
            parse_mode="Markdown")
        return

    await state.clear()

    period_code = f"{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}"
    period_name = f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"

    stats = await get_dashboard_stats(session, start_date, end_date)
    profitability = (stats["profit"] / stats["revenue"] * 100) if stats["revenue"] > 0 else 0

    report_text = (
        f"📊 **{period_name} UCHUN NATIJALAR**:\n\n"
        f"💰 Aylanma (Tushum): **{int(stats['revenue']):,} so'm**\n"
        f"📉 Mahsulot xarajatlari: **{int(stats['cost']):,} so'm**\n"
        f"⛽️ Benzin xarajatlari: **{int(stats['fuel']):,} so'm**\n"
    )

    if stats.get('other_exp', 0) > 0:
        report_text += f"🛠 Boshqa xarajatlar: **{int(stats['other_exp']):,} so'm**\n"

    report_text += (
        f"───────────────────\n"
        f"🏆 **SOF FOYDA: {int(stats['profit']):,} so'm**\n\n"
        f"📈 Biznes rentabelligi: **{profitability:.1f}%**"
    )

    from keyboards.inline import get_dashboard_kb
    await message.answer(report_text, reply_markup=get_dashboard_kb(period_code), parse_mode="Markdown")


# --- УМНЫЙ ПАРСЕР ДАТ ---
def parse_dates_from_period(period: str):
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    if period == "today":
        return today_start, today_end

    elif period == "yesterday":
        yesterday_start = today_start - timedelta(days=1)
        yesterday_end = yesterday_start.replace(hour=23, minute=59, second=59, microsecond=999999)
        return yesterday_start, yesterday_end

    elif period == "month":
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return month_start, today_end

    elif "-" in period:
        try:
            start_str, end_str = period.split("-")
            start = datetime.strptime(start_str, "%Y%m%d").replace(hour=0, minute=0, second=0, microsecond=0)
            end = datetime.strptime(end_str, "%Y%m%d").replace(hour=23, minute=59, second=59, microsecond=999999)
            return start, end
        except:
            return today_start, today_end

    return today_start, today_end

# --- ГЕНЕРАТОР EXCEL ---
@router.callback_query(F.data.startswith("adm_stats_dl_xlsx:")) # НА СЕРВАК
@router.callback_query(F.data == "adm_stats_export_all:xlsx")
async def admin_export_universal_excel(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer("⏳ Batafsil hisobot tayyorlanyapti...", show_alert=False)

    if "dl_xlsx" in callback.data:
        period = callback.data.split(":")[1]
        start_date, end_date = parse_dates_from_period(period)
        filename_prefix = f"Hisobot_{start_date.strftime('%d%m')}" if start_date.date() == end_date.date() else f"Hisobot_{start_date.strftime('%d%m')}-{end_date.strftime('%d%m')}"
    else:
        start_date, end_date = None, None
        filename_prefix = "Global_Hisobot"

    raw_data = await get_all_deliveries_for_export(session, start_date, end_date)

    if not raw_data:
        await callback.answer("❌ Ushbu davr uchun birorta ham yetkazib berish topilmadi.", show_alert=True)
        return

    df = pd.DataFrame(raw_data)

    mapping = {
        'Дата': 'Sana',
        'Водитель': 'Haydovchi',
        'Садик': 'Bog\'cha',
        'Товар': 'Mahsulot',
        'Ед_изм': 'O\'lchov_birligi',
        'План': 'Reja',
        'Факт': 'Fakt',
        'Цена_Садик': 'Bog\'cha_narxi',
        'Цена_Закуп': 'Xarid_narxi',
        'Выручка': 'Tushum',
        'Закуп_сумма': 'Xarid_summasi',
        'Бензин_Смены': 'Smena_benzini',
        'Другие_Расходы': 'Boshqa_xarajatlar',
        'Комментарий_Расходов': 'Xarajat_izohi'
    }
    df = df.rename(columns=mapping)

    df['Sana'] = pd.to_datetime(df['Sana']).dt.strftime('%d.%m.%Y %H:%M')

    df['Smena_benzini'] = df['Smena_benzini'].fillna(0).astype(float)
    df['Boshqa_xarajatlar'] = df['Boshqa_xarajatlar'].fillna(0).astype(float)

    shift_counts = df.groupby('shift_id')['shift_id'].transform('count')

    df['Benzin (ulushi)'] = df['Smena_benzini'] / shift_counts
    df['Boshqa (ulushi)'] = df['Boshqa_xarajatlar'] / shift_counts

    df['Foyda_Marja'] = df['Tushum'] - df['Xarid_summasi'] - df['Benzin (ulushi)'] - df['Boshqa (ulushi)']

    df = df.drop(columns=['shift_id', 'Smena_benzini', 'Boshqa_xarajatlar'])

    kg_summary = df.groupby("Bog'cha").agg({
        "Tushum": "sum", "Xarid_summasi": "sum",
        "Benzin (ulushi)": "sum", "Boshqa (ulushi)": "sum",  # Добавили
        "Foyda_Marja": "sum", "Fakt": "count"
    }).rename(columns={"Fakt": "Yetkazib_berishlar_soni"}).reset_index()

    prod_summary = df.groupby("Mahsulot").agg({
        "Fakt": "sum", "Tushum": "sum", "Xarid_summasi": "sum",
        "Benzin (ulushi)": "sum", "Boshqa (ulushi)": "sum",  # Добавили
        "Foyda_Marja": "sum"
    }).reset_index()

    def add_total_row(target_df, label_col, label_text):
        numeric_cols = target_df.select_dtypes(include=['number']).columns
        totals = target_df[numeric_cols].sum()
        total_row = {col: totals[col] for col in numeric_cols}
        total_row[label_col] = label_text
        return pd.concat([target_df, pd.DataFrame([total_row])], ignore_index=True)

    df = add_total_row(df, 'Sana', 'JAMI:')
    kg_summary = add_total_row(kg_summary, "Bog'cha", 'JAMI:')
    prod_summary = add_total_row(prod_summary, "Mahsulot", 'JAMI:')

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Umumiy log", index=False)
        kg_summary.to_excel(writer, sheet_name="Bog'chalar bo'yicha", index=False)
        prod_summary.to_excel(writer, sheet_name="Mahsulotlar bo'yicha", index=False)

        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            for col in worksheet.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
                worksheet.column_dimensions[column].width = max_length + 3

    output.seek(0)
    document = BufferedInputFile(output.getvalue(), filename=f"{filename_prefix}.xlsx")

    await callback.message.answer_document(document, caption="✅ Excel-hisobot tayyor!")
    # "✅ Excel-отчет успешно сформирован."


# --- ГЕНЕРАТОР PDF ---
@router.callback_query(F.data.startswith("adm_stats_dl_pdf:"))
@router.callback_query(F.data == "adm_stats_export_all:pdf")
async def admin_export_universal_pdf(callback: types.CallbackQuery, session: AsyncSession):
    await callback.answer("⏳ Batafsil PDF tayyorlanyapti (3 ta bo'lim)...", show_alert=False)

    if "dl_pdf" in callback.data:
        period = callback.data.split(":")[1]
        start_date, end_date = parse_dates_from_period(period)

        if start_date.date() == end_date.date():
            title = f"{start_date.strftime('%d.%m.%Y')} SANA UCHUN HISOBOT"
            filename_prefix = f"Hisobot_{start_date.strftime('%d%m')}"
        else:
            title = f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')} DAVRI UCHUN HISOBOT"
            filename_prefix = f"Hisobot_{start_date.strftime('%d%m')}-{end_date.strftime('%d%m')}"
    else:
        start_date, end_date = None, None
        title = "UMUMIY HISOBOT (BARCHA VAQT UCHUN)"
        filename_prefix = "Umumiy_Hisobot"

    raw_data = await get_all_deliveries_for_export(session, start_date, end_date)
    if not raw_data:
        await callback.answer("❌ Ushбу davr uchun ma'lumot topilmadi.", show_alert=True)
        return

    df = pd.DataFrame(raw_data)

    df = df.rename(columns={
        'Дата': 'Sana',
        'Водитель': 'Haydovchi',
        'Садик': 'Bog\'cha',
        'Товар': 'Mahsulot',
        'Ед_изм': 'O\'lchov_birligi',
        'План': 'Reja',
        'Факт': 'Fakt',
        'Цена_Садик': 'Bog\'cha_narxi',
        'Цена_Закуп': 'Xarid_narxi',
        'Бензин_Смены': 'Smena_benzini',
        'Другие_Расходы': 'Boshqa_xarajatlar',
        'Комментарий_Расходов': 'Xarajat_izohi',
        'Выручка': 'Tushum',
        'Закуп_сумма': 'Xarid_summasi'
    })

    df['Sana'] = pd.to_datetime(df['Sana']).dt.strftime('%d.%m %H:%M')
    df['Smena_benzini'] = df['Smena_benzini'].fillna(0).astype(float)
    df['Boshqa_xarajatlar'] = df['Boshqa_xarajatlar'].fillna(0).astype(float)
    df['Xarajat_izohi'] = df['Xarajat_izohi'].fillna("")

    shift_counts = df.groupby('shift_id')['shift_id'].transform('count')
    df['Benzin (ulushi)'] = df['Smena_benzini'] / shift_counts
    df['Boshqa (ulushi)'] = df['Boshqa_xarajatlar'] / shift_counts
    df['Sof_foyda_marja'] = df['Tushum'] - df['Xarid_summasi'] - df['Benzin (ulushi)'] - df['Boshqa (ulushi)']
    df = df.drop(columns=['shift_id', 'Smena_benzini', 'Boshqa_xarajatlar'])

    def add_jami(target_df, label_col):
        numeric_cols = target_df.select_dtypes(include=['number']).columns
        totals = target_df[numeric_cols].sum()
        new_row = {col: totals[col] for col in numeric_cols}
        new_row[label_col] = 'JAMI:'
        return pd.concat([target_df, pd.DataFrame([new_row])], ignore_index=True)

    kg_summary = df.groupby("Bog'cha").agg({
        "Tushum": "sum", "Xarid_summasi": "sum", "Benzin (ulushi)": "sum",
        "Boshqa (ulushi)": "sum", "Sof_foyda_marja": "sum", "Fakt": "count"
    }).rename(columns={"Fakt": "Soni"}).reset_index()

    prod_summary = df.groupby("Mahsulot").agg({
        "Fakt": "sum", "Tushum": "sum", "Xarid_summasi": "sum",
        "Benzin (ulushi)": "sum", "Boshqa (ulushi)": "sum", "Sof_foyda_marja": "sum"
    }).reset_index()

    full_df = add_jami(df, 'Sana')
    kg_summary = add_jami(kg_summary, "Bog'cha")
    prod_summary = add_jami(prod_summary, "Mahsulot")

    pdf = FPDF(orientation="L")
    pdf.add_page()
    pdf.add_font('MyArial', '', "fonts/arial.ttf", uni=True)

    def fmt(val, is_num=True, max_len=15):
        if pd.isna(val): return ""
        if is_num:
            try:
                return f"{int(float(val)):,}"
            except: return "0"
        return str(val)[:max_len]

    pdf.set_font('MyArial', '', 14)
    pdf.cell(0, 10, title + " - 1-SAHIFA (UMUMIY LOG)", ln=True, align='C')
    pdf.ln(2)

    pdf.set_font('MyArial', '', 6) # Немного уменьшили шрифт для плотности
    headers = [
        ("Sana", 18), ("Haydovchi", 20), ("Bog'cha", 24), ("Mahsulot", 22),
        ("Birl.", 7), ("Reja", 9), ("Fakt", 9), ("Bog'.N", 16),
        ("Xar.N", 16), ("Tushum", 18), ("Xarid", 18), ("Benz.", 15),
        ("Boshqa", 15), ("Izoh", 48), ("Marja", 22) # Изменили ширину и добавили Izoh
    ]

    for h, w in headers:
        pdf.cell(w, 7, h, 1, align='C')
    pdf.ln()

    for _, row in full_df.iterrows():
        if pdf.get_y() > 180:
            pdf.add_page()
            for h, w in headers: pdf.cell(w, 7, h, 1, align='C')
            pdf.ln()

        pdf.cell(18, 6, fmt(row.get('Sana'), False, 11), 1)
        pdf.cell(20, 6, fmt(row.get('Haydovchi'), False, 12), 1)
        pdf.cell(24, 6, fmt(row.get('Bog\'cha'), False, 15), 1)
        pdf.cell(22, 6, fmt(row.get('Mahsulot'), False, 15), 1)
        pdf.cell(7, 6, fmt(row.get('O\'lchov_birligi'), False, 3), 1, align='C')
        pdf.cell(9, 6, fmt(row.get('Reja'), False), 1, align='C')
        pdf.cell(9, 6, fmt(row.get('Fakt'), False), 1, align='C')
        pdf.cell(16, 6, fmt(row.get('Bog\'cha_narxi')), 1, align='R')
        pdf.cell(16, 6, fmt(row.get('Xarid_narxi')), 1, align='R')
        pdf.cell(18, 6, fmt(row.get('Tushum')), 1, align='R')
        pdf.cell(18, 6, fmt(row.get('Xarid_summasi')), 1, align='R')
        pdf.cell(15, 6, fmt(row.get('Benzin (ulushi)')), 1, align='R')
        pdf.cell(15, 6, fmt(row.get('Boshqa (ulushi)')), 1, align='R')
        pdf.cell(48, 6, fmt(row.get('Xarajat_izohi'), False, 35), 1) # <--- ВЫВОД КОММЕНТАРИЯ
        pdf.cell(22, 6, fmt(row.get('Sof_foyda_marja')), 1, align='R')
        pdf.ln()

    pdf.add_page()
    pdf.set_font('MyArial', '', 14)
    pdf.cell(0, 10, "2-SAHIFA: BOG'CHALAR BO'YICHA YAKUNLAR", ln=True, align='C')
    pdf.ln(5)

    pdf.set_font('MyArial', '', 10)
    kg_headers = [("Bog'cha", 60), ("Soni", 15), ("Tushum", 35), ("Xarid", 35), ("Benzin", 30), ("Boshqa", 30),
                  ("Marja", 35)]
    for h, w in kg_headers: pdf.cell(w, 8, h, 1, align='C')
    pdf.ln()

    for _, row in kg_summary.iterrows():
        pdf.cell(60, 8, fmt(row.get('Bog\'cha'), False, 30), 1)
        pdf.cell(15, 8, fmt(row.get('Soni'), False), 1, align='C')
        pdf.cell(35, 8, fmt(row.get('Tushum')), 1, align='R')
        pdf.cell(35, 8, fmt(row.get('Xarid_summasi')), 1, align='R')
        pdf.cell(30, 8, fmt(row.get('Benzin (ulushi)')), 1, align='R')
        pdf.cell(30, 8, fmt(row.get('Boshqa (ulushi)')), 1, align='R')
        pdf.cell(35, 8, fmt(row.get('Sof_foyda_marja')), 1, align='R')
        pdf.ln()

    pdf.add_page()
    pdf.set_font('MyArial', '', 14)
    pdf.cell(0, 10, "3-SAHIFA: MAHSULOTLAR BO'YICHA YAKUNLAR", ln=True, align='C')
    pdf.ln(5)

    pdf.set_font('MyArial', '', 10)
    prod_headers = [("Mahsulot", 60), ("Fakt", 15), ("Tushum", 35), ("Xarid", 35), ("Benzin", 30), ("Boshqa", 30),
                    ("Marja", 35)]
    for h, w in prod_headers: pdf.cell(w, 8, h, 1, align='C')
    pdf.ln()

    for _, row in prod_summary.iterrows():
        pdf.cell(60, 8, fmt(row.get('Mahsulot'), False, 30), 1)
        pdf.cell(15, 8, fmt(row.get('Fakt'), False), 1, align='C')
        pdf.cell(35, 8, fmt(row.get('Tushum')), 1, align='R')
        pdf.cell(35, 8, fmt(row.get('Xarid_summasi')), 1, align='R')
        pdf.cell(30, 8, fmt(row.get('Benzin (ulushi)')), 1, align='R')
        pdf.cell(30, 8, fmt(row.get('Boshqa (ulushi)')), 1, align='R')
        pdf.cell(35, 8, fmt(row.get('Sof_foyda_marja')), 1, align='R')
        pdf.ln()

    pdf_output = pdf.output(dest='S')
    document = BufferedInputFile(pdf_output, filename=f"{filename_prefix}.pdf")
    await callback.message.answer_document(document, caption="✅ Batafsil PDF-hisobot tayyorlandi (3 ta sahifa).")
