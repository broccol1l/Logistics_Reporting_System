from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, func
from sqlalchemy.orm import selectinload
from database.models import User
from datetime import datetime, timedelta
from keyboards import inline  # Твои новые инлайны


from database import requests
from database.models import Product, Kindergarten, Delivery, Shift
from utils.states import DeliveryState
from keyboards.reply import main_menu_kb
from keyboards.inline import (
    get_kg_paging_kb, KGOrderCallback,
    get_products_paging_kb, ProductCallback, get_loop_kb
)

router = Router()


async def show_kindergartens(message: types.Message, state: FSMContext, session: AsyncSession):
    # Вызываем функцию, которая у тебя точно есть в requests.py
    from database.requests import get_active_kindergartens
    kgs = await get_active_kindergartens(session)

    # Устанавливаем твой реальный стейт "Выбор садика"
    await state.set_state(DeliveryState.object_name)

    # Отправляем список садиков
    await message.answer(
        "Yuk tushirishni boshlash uchun bog'chani tanlang:",
        reply_markup=get_kg_paging_kb(kgs, page=0)
    )
    #Выберите садик для начала отгрузки:


@router.message(F.text == "📦 Yuk qo'shish") # 📦 Добавить отгрузку
async def start_delivery_with_date(message: types.Message, state: FSMContext, session: AsyncSession):
    user = await requests.get_user(session, message.from_user.id)
    shift = await requests.get_active_shift(session, user.id)

    if shift:
        # ОБЯЗАТЕЛЬНО сохраняем id смены в стейт, если она уже открыта
        await state.update_data(shift_id=shift.id)
        await show_kindergartens(message, state, session)
    else:
        await message.answer(
            "Yuklarni qaysi kun uchun kiritamiz?",
            reply_markup=inline.get_date_selection_kb()
        )
        # За какой день вводим отгрузки?

@router.callback_query(F.data.startswith("set_date:"))
async def set_shift_date(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    date_type = callback.data.split(":")[1]
    target_date = datetime.now() if date_type == "today" else datetime.now() - timedelta(days=1)
    user = await requests.get_user(session, callback.from_user.id)

    # Создаем смену и получаем её объект
    shift = await requests.create_shift_with_date(session, user.id, target_date)
    # Сохраняем id новой смены в стейт
    await state.update_data(shift_id=shift.id)

    await callback.message.edit_text(f"✅ Smena {target_date.strftime('%d.%m.%Y')} sanasiga ochildi")
    #✅ Смена открыта на {target_date.strftime('%d.%m.%Y')}
    await show_kindergartens(callback.message, state, session)

# 2. Обработка выбора садика
@router.callback_query(KGOrderCallback.filter(), DeliveryState.object_name)
async def delivery_object_chosen(callback: types.CallbackQuery, callback_data: KGOrderCallback,
                                 state: FSMContext, session: AsyncSession):
    if callback_data.action == "nav":
        kgs = await requests.get_active_kindergartens(session)
        await callback.message.edit_reply_markup(
            reply_markup=get_kg_paging_kb(kgs, page=callback_data.page)
        )
        await callback.answer()
        return

    kg = await session.get(Kindergarten, callback_data.kg_id)
    await state.update_data(kindergarten_id=kg.id, kg_name=kg.name)

    products = await requests.get_all_products(session)
    await state.set_state(DeliveryState.choosing_product)

    await callback.message.edit_text(
        f"🏢 Obyekt: <b>{kg.name}</b>\nEndi mahsulotni tanlang:",
        reply_markup=get_products_paging_kb(products),
        parse_mode="HTML"
    )
    # 🏢 Объект: {kg.name}\nТеперь выберите товар:
    await callback.answer()


# 3. Обработка выбора товара
@router.callback_query(ProductCallback.filter(), DeliveryState.choosing_product)
async def product_chosen(callback: types.CallbackQuery, callback_data: ProductCallback,
                         state: FSMContext, session: AsyncSession):
    if callback_data.action == "nav":
        products = await requests.get_all_products(session)
        await callback.message.edit_reply_markup(
            reply_markup=get_products_paging_kb(products, page=callback_data.page)
        )
        await callback.answer()
        return

    product = await session.get(Product, callback_data.prod_id)
    await state.update_data(product_id=product.id, prod_name=product.name, unit=product.unit)

    await state.set_state(DeliveryState.weight_plan)
    await callback.message.edit_text(
        f"📦 Mahsulot: <b>{product.name}</b>\nMahsulot: ({product.unit}da):",
        parse_mode="HTML"
    )
    # f"📦 Товар: <b>{product.name}</b>\nВведите план (в {product.unit}):"
    await callback.answer()


# 4. Ввод ПЛАНА
@router.message(DeliveryState.weight_plan)
async def delivery_plan_chosen(message: types.Message, state: FSMContext):
    data = await state.get_data()
    unit = data.get('unit')
    try:
        weight = float(message.text.replace(',', '.'))
        await state.update_data(weight_plan=weight)
        await state.set_state(DeliveryState.weight_fact)
        await message.answer(
            f"{weight} {unit} reja qabul qilindi.\n<b>Haqiqiy vazn/miqdorni</b> kiriting:",
            parse_mode="HTML"
        )

        #f"План {weight} {unit} принят.\nВведите <b>фактический вес/кол-во</b>:"
    except ValueError:
        await message.answer(f"Xato! Son kiriting ({unit}). Misol uchun: 15.5")
        # f"Ошибка! Введите число ({unit}). Пример: 15.5"


# 5. Ввод ФАКТА и сохранение в базу (Snapshot)
@router.message(DeliveryState.weight_fact, F.text, ~F.text.contains("Yakunlash")) #Завершить
async def delivery_fact_chosen(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    unit = data.get('unit', 'кг')
    try:
        weight_fact = float(message.text.replace(',', '.'))
        if weight_fact > data['weight_plan']:
            await message.answer(f"❌ Haqiqiy miqdor rejadan ko'p bo'lishi mumkin emas ({data['weight_plan']} {unit}). "
                                 f"Qaytadan kiriting:")
            #f"❌ Факт не может быть больше плана ({data['weight_plan']} {unit}). Введите заново:"
            return

        # Сохраняем отгрузку
        delivery = await requests.add_delivery(
            session, data['shift_id'], data['product_id'],
            data['kindergarten_id'], data['weight_plan'], weight_fact
        )

        # --- ВОТ ЭТО ДОБАВЬ ---
        # Очищаем стейт, чтобы нижнее меню (Мои отчеты и т.д.) снова работало
        # Но сохраняем shift_id и kindergarten_id в памяти на случай,
        # если юзер нажмет инлайновую кнопку "Добавить еще товар"
        await state.set_state(None)
        # ----------------------

        await message.answer(
            f"✅ Saqlandi: {data['prod_name']}\n"
            f"Summa: <b>{delivery.total_price_sadik:,} сум</b>\n\n"
            "Ushbu bog'chaga yana mahsulot qo'shasizmi?",
            reply_markup=get_loop_kb(),
            parse_mode="HTML"
        )
        # f"✅ Сохранено: {data['prod_name']}\n"
        # f"Сумма: <b>{delivery.total_price_sadik:,} сум</b>\n\n"
        # "Добавить ещё товар в этот садик?",
    except ValueError:
        await message.answer(f"Ошибка! Введите число ({unit}).")


@router.callback_query(F.data == "add_more_prod")
async def add_more_product(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()

    # ПРОВЕРКА: Если садик потерялся (например, при редактировании)
    if 'kindergarten_id' not in data:
        await callback.answer("Avval bog'chani tanlang") # Сначала выберите садик
        await show_kindergartens(callback.message, state, session)
        return

    # Если садик на месте, просто показываем товары как обычно
    await state.set_state(DeliveryState.choosing_product)
    from database.requests import get_all_products
    products = await get_all_products(session)
    await callback.message.edit_text(
        "Mahsulotni tanlang:",
        reply_markup=get_products_paging_kb(products, page=0)
    )
    # Выберите товар:


@router.callback_query(F.data == "finish_this_kg")
async def finish_kg(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    # 1. Берем данные для финального отчета по садику
    data = await state.get_data()
    shift_id = data.get('shift_id')
    kg_id = data.get('kindergarten_id')
    kg_name = data.get('kg_name')

    # 2. Собираем все позиции, что водитель ввел за этот заезд
    query = select(Delivery).where(
        Delivery.shift_id == shift_id,
        Delivery.kindergarten_id == kg_id
    ).options(selectinload(Delivery.product))

    result = await session.execute(query)
    deliveries = result.scalars().all()

    if not deliveries:
        await callback.message.answer("Ushbu bog'chaga hech narsa yetkazilmadi.", reply_markup=main_menu_kb())
        # В этот садик ничего не было отгружено.
    else:
        report = f"🏁 <b>Obyekt bo'yicha yakun: {kg_name}</b>\n\n" # 🏁 Итог по объекту: {kg_name}
        total_kg_sum = 0
        for d in deliveries:
            report += f"🔹 {d.product.name}: {d.weight_fact} {d.product.unit} — <b>{d.total_price_sadik:,} so'm</b>\n"
            # сум
            total_kg_sum += d.total_price_sadik

        report += f"\n💰 <b>To'lov uchun jami: {total_kg_sum:,} so'm</b>" # 💰 Итого к оплате:
        await callback.message.answer(report, reply_markup=main_menu_kb(), parse_mode="HTML")

    # 3. Полная очистка стейта только в самом конце
    await state.clear()
    await callback.answer()


from keyboards.reply import main_menu_kb  # убедись, что импорт есть

@router.message(F.text == "🏁 Smenani yopish") # 🏁 Завершить смену
async def close_shift_button_handler(message: types.Message, state: FSMContext, session: AsyncSession):
    await close_shift_start(message, state, session)


# 1. Начало закрытия смены (обработка и кнопки, и инлайна)
@router.message(F.text == "🏁 Smenani yopish") # НА СЕРВАК
async def close_shift_start(message: types.Message, state: FSMContext, session: AsyncSession,
                            manual_user_id: int = None):
    # Если manual_user_id передан (из инлайна), берем его. Иначе из сообщения.
    tg_id = manual_user_id if manual_user_id else message.from_user.id
    user = await requests.get_user(session, tg_id)
    # Ищем активную смену
    shift = await requests.get_active_shift(session, user.id)

    if not shift:
        await message.answer("Sizda ochiq smenalar yo'q.") # До: У вас нет открытых смен.
        return

    await state.update_data(shift_id=shift.id)
    await state.set_state(DeliveryState.waiting_fuel)

    kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="0 (yoqilg'i quyilmadi)")]], # До: 0 (не заправлялся)
        resize_keyboard=True
    )
    await message.answer(
        "Bugungi benzin xarajatini kiriting (so'mda).\n"
        "Agar xarajat bo'lmagan bo'lsa, 0 kiriting yoki pastdagi tugmani bosing:",
        reply_markup=kb
    )

# 2. Обработка бензина и вопрос про другие расходы
@router.message(DeliveryState.waiting_fuel) # НА СЕРВАК
async def process_fuel(message: types.Message, state: FSMContext):
    try:
        fuel_text = message.text.split(' ')[0]
        clean_fuel = fuel_text.replace('.', '').replace(',', '')
        fuel_amount = float(clean_fuel)

        # Сохраняем бензин в память
        await state.update_data(fuel_amount=fuel_amount)

        # Переходим к доп. расходам
        await state.set_state(DeliveryState.waiting_other_amount)

        kb = types.ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text="0 (boshqa xarajat yo'q)")]],
            resize_keyboard=True
        )
        await message.answer(
            "Boshqa xarajatlar bormi? (remont, obed, jarima va h.k.)\n"
            "Agar bo'lsa summasini yozing, bo'lmasa 0 kiriting:",
            reply_markup=kb
        )
    except ValueError:
        await message.answer("Xato! Faqat raqam kiriting (masalan: 50000).")


# 3. Обработка доп. расходов
@router.message(DeliveryState.waiting_other_amount) # НА СЕРВАК
async def process_other_amount(message: types.Message, state: FSMContext, session: AsyncSession): # НА СЕРВАк
    try:
        exp_text = message.text.split(' ')[0]
        clean_exp = exp_text.replace('.', '').replace(',', '')
        other_amount = float(clean_exp)

        await state.update_data(other_amount=other_amount)

        if other_amount > 0:
            # Если есть расход, спрашиваем на что
            await state.set_state(DeliveryState.waiting_other_comment)
            await message.answer("Bu xarajat nima uchun qilindi? (qisqa yozing):",
                                 reply_markup=types.ReplyKeyboardRemove())
        else:
            # Если расхода нет, сразу закрываем смену (передаем message искусственно)
            await state.update_data(other_comment="")
            await close_shift_final(message, state, session)
    except ValueError:
        await message.answer("Xato! Faqat raqam kiriting.")

# 4. Обработка комментария
@router.message(DeliveryState.waiting_other_comment)
async def process_other_comment(message: types.Message, state: FSMContext, session: AsyncSession): # НА СЕРВАК
    await state.update_data(other_comment=message.text)
    await close_shift_final(message, state, session)

# Вспомогательная функция финала
async def close_shift_final(message: types.Message, state: FSMContext, session: AsyncSession): # НА СЕРВАК
    data = await state.get_data()
    shift_id = data.get('shift_id')
    fuel_amount = data.get('fuel_amount', 0.0)
    other_amount = data.get('other_amount', 0.0)
    other_comment = data.get('other_comment', '')

    deliveries = await requests.get_shift_deliveries(session, shift_id)
    user = await requests.get_user(session, message.from_user.id)

    if not deliveries:
        # ПЕРЕДАЕМ РАЗДЕЛЬНО: бензин, доп. расходы и комментарий
        await requests.close_shift(session, shift_id, fuel_amount, other_amount, other_comment)
        await state.clear()
        await message.answer("🏁 Smena yopildi. Bugun yetkazib berishlar bo'lmadi.",
                             reply_markup=main_menu_kb(user.is_admin))
        return

    report = "📝 <b>ISH KUNINGIZ YAKUNI:</b>\n\n"
    kg_data = {}
    total_shift_sum = 0

    for d in deliveries:
        kg_name = d.kindergarten.name
        if kg_name not in kg_data:
            kg_data[kg_name] = {"items": [], "total": 0}
        price = d.total_price_sadik
        # Сразу обернул price в int(), чтобы не было .0
        kg_data[kg_name]["items"].append(
            f"  ◦ {d.product.name}: {d.weight_fact} {d.product.unit} — <b>{int(price):,} so'm</b>")
        kg_data[kg_name]["total"] += price
        total_shift_sum += price

    for name, info in kg_data.items():
        report += f"🏫 <b>{name}</b>\n"
        report += "\n".join(info["items"]) + "\n"
        report += f"   🏷 Jami: <b>{int(info['total']):,} so'm</b>\n\n"

    # Считаем чистую сумму
    total_expenses = fuel_amount + other_amount
    final_net_amount = total_shift_sum - total_expenses

    # Убрал везде лишние .0 через int()
    report += f"💰 Umumiy tushum: {int(total_shift_sum):,} so'm\n"
    report += f"⛽ Benzin: -{int(fuel_amount):,} so'm\n"
    if other_amount > 0:
        report += f"🛠 Boshqa xarajatlar: -{int(other_amount):,} so'm ({other_comment})\n"
    report += "───────────────────\n"
    report += f"💵 <b>TOPSHIRILADIGAN JAMI SUMMA: {int(final_net_amount):,} so'm</b>\n\n"
    report += "🏁 Smena yopildi. Maroqli hordiq chiqaring!"

    # ПЕРЕДАЕМ РАЗДЕЛЬНО: бензин, доп. расходы и комментарий
    await requests.close_shift(session, shift_id, fuel_amount, other_amount, other_comment)
    await state.clear()
    await message.answer(report, reply_markup=main_menu_kb(user.is_admin), parse_mode="HTML")

# Показываем садики, которые уже ввел водитель в этой смене
@router.callback_query(F.data == "manage_current_shift")
async def manage_current(callback: types.CallbackQuery, session: AsyncSession):
    user = await requests.get_user(session, callback.from_user.id)
    shift = await requests.get_or_create_shift(session, user.id)
    deliveries = await requests.get_shift_deliveries(session, shift.id)

    if not deliveries:
        await callback.answer("Ushbu smenada hali yozuvlar yo'q.", show_alert=True) # В этой смене еще нет записей.
        return

    kgs = {d.kindergarten.id: d.kindergarten.name for d in deliveries}

    builder = InlineKeyboardBuilder()
    for kg_id, kg_name in kgs.items():
        builder.button(text=f"❌ {kg_name}ni o'chirish", callback_data=f"del_kg_curr:{kg_id}") # f"❌ Удалить {kg_name}"
    builder.button(text="⬅️ Назад", callback_data="back_to_loop")  # Сделай хендлер для возврата к кнопкам петли
    builder.adjust(1)

    await callback.message.edit_text("O'chirish uchun bog'chani tanlang:", reply_markup=builder.as_markup())
    # Выберите садик для удаления:


# Удаление садика
@router.callback_query(F.data.startswith("del_kg_curr:"))
async def delete_kg_curr(callback: types.CallbackQuery, session: AsyncSession):
    kg_id = int(callback.data.split(":")[1])
    user = await requests.get_user(session, callback.from_user.id)
    shift = await requests.get_or_create_shift(session, user.id)
    await requests.delete_kg_from_active_shift(session, shift.id, kg_id)
    await callback.answer("Bog'cha o'chirildi!", show_alert=True) # "Садик удален!"
    await manage_current(callback, session)  # Обновляем список


# 1. Кнопка "Назад" в основную петлю (исправляем твою ошибку)
@router.callback_query(F.data == "back_to_loop")
async def back_to_loop_handler(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Ma'lumotlar saqlandi. Keyingi qadam nima?", # Данные сохранены. Что делаем дальше?
        reply_markup=get_loop_kb()  # Твоя функция с 4-мя кнопками
    )


# 2. Список садиков (Первый уровень просмотра)
@router.callback_query(F.data == "manage_current_shift")
async def manage_current(callback: types.CallbackQuery, session: AsyncSession):
    user = await requests.get_user(session, callback.from_user.id)
    shift = await requests.get_or_create_shift(session, user.id)
    deliveries = await requests.get_shift_deliveries(session, shift.id)

    if not deliveries:
        await callback.answer("Bu smena hozircha bo'sh", show_alert=True) # В этой смене пока пусто
        return

    # Группируем садики
    kgs = {d.kindergarten.id: d.kindergarten.name for d in deliveries}

    builder = InlineKeyboardBuilder()
    for kg_id, kg_name in kgs.items():
        builder.button(text=f"🏫 {kg_name}", callback_data=f"view_kg_det:{kg_id}")

    builder.button(text="⬅️ Ortga", callback_data="back_to_loop") # ⬅️ Назад
    builder.adjust(1)

    await callback.message.edit_text(
        "🔍 **Joriy smenani ko'rish:**\nTafsilotlarni ko'rish yoki o'chirish uchun bog'chani tanlang.",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    # "🔍 **Просмотр текущей смены:**\nВыберите садик, чтобы увидеть детали или удалить его."


# 3. Детали конкретного садика (Второй уровень просмотра)
@router.callback_query(F.data.startswith("view_kg_det:"))
async def view_kg_details(callback: types.CallbackQuery, session: AsyncSession):
    kg_id = int(callback.data.split(":")[1])
    user = await requests.get_user(session, callback.from_user.id)
    shift = await requests.get_or_create_shift(session, user.id)

    # Получаем товары только этого садика
    items = await requests.get_kg_deliveries_in_shift(session, shift.id, kg_id)

    if not items:
        await callback.answer("Ma'lumotlar topilmadi") # Данные не найдены
        return

    kg_name = items[0].kindergarten.name
    res_text = f"🏫 **Bog'cha: {kg_name}**\n\n" # Садик
    kg_total = 0

    for row in items:
        res_text += f"• {row.product.name}: {row.weight_fact} {row.product.unit} — {row.total_price_sadik:,} сум\n"
        kg_total += row.total_price_sadik

    res_text += f"\n💰 **Bog'cha bo'yicha jami: {kg_total:,} so'm**" # f"\n💰 **Итого по садику: {kg_total:,} сум**"

    builder = InlineKeyboardBuilder()
    # Кнопка удаления именно этого садика
    builder.button(text="🗑 Ushbu bog'chani o'chirish", callback_data=f"del_kg_curr:{kg_id}") # До: 🗑 Удалить этот садик
    builder.button(text="⬅️ Ro'yxatga qaytish", callback_data="manage_current_shift") # До: ⬅️ Назад к списку
    builder.adjust(1)

    await callback.message.edit_text(res_text, reply_markup=builder.as_markup(), parse_mode="Markdown")


# 4. Само удаление (уже исправленное с kindergarten_id)
@router.callback_query(F.data.startswith("del_kg_curr:"))
async def delete_kg_curr(callback: types.CallbackQuery, session: AsyncSession):
    kg_id = int(callback.data.split(":")[1])
    user = await requests.get_user(session, callback.from_user.id)
    shift = await requests.get_or_create_shift(session, user.id)

    # Твоя исправленная колонка kindergarten_id
    await requests.delete_kg_from_active_shift(session, shift.id, kg_id)

    await callback.answer("Bog'cha smenadan butunlay o'chirildi", show_alert=True) # Садик полностью удален из смены
    # Возвращаем водителя к списку оставшихся садиков
    await manage_current(callback, session)


# 1. Список садиков в текущей смене
@router.callback_query(F.data == "manage_current_shift")
async def manage_current(callback: types.CallbackQuery, session: AsyncSession):
    user = await requests.get_user(session, callback.from_user.id)
    shift = await requests.get_active_shift(session, user.id)
    deliveries = await requests.get_shift_deliveries(session, shift.id)

    if not deliveries:
        await callback.answer("В этой смене пока нет записей.", show_alert=True)
        return

    # Собираем словарь садиков {id: имя}
    kgs = {d.kindergarten.id: d.kindergarten.name for d in deliveries}

    # Вызываем твой инлайн из inline.py
    await callback.message.edit_text(
        "🔍 **Joriy smenani ko'rish:**\nTafsilotlarni ko'rish yoki o'chirish uchun bog'chani tanlang.",
        reply_markup=inline.get_manage_current_kb(kgs),
        parse_mode="Markdown"
    )
    # "🔍 **Просмотр текущей смены:**\nВыберите садик для деталей или удаления."


# 2. Детали садика и кнопка "Удалить"
@router.callback_query(F.data.startswith("view_kg_det:"))
async def view_kg_details(callback: types.CallbackQuery, session: AsyncSession):
    kg_id = int(callback.data.split(":")[1])
    user = await requests.get_user(session, callback.from_user.id)
    shift = await requests.get_active_shift(session, user.id)

    # Получаем товары этого садика (функцию добавь в requests.py)
    items = await requests.get_kg_deliveries_in_shift(session, shift.id, kg_id)

    kg_name = items[0].kindergarten.name
    res_text = f"🏫 **Bog'cha: {kg_name}**\n\n" # Садик
    kg_total = 0
    for row in items:
        res_text += f"• {row.product.name}: {row.weight_fact} {row.product.unit} — {row.total_price_sadik:,} so'm\n"
        kg_total += row.total_price_sadik

    res_text += f"\n💰 **Jami: {kg_total:,} so'm**"

    # Вызываем клавиатуру удаления
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Ushbu bog'chani o'chirish", callback_data=f"del_kg_curr:{kg_id}") # До: 🗑 Удалить этот садик
    builder.button(text="⬅️ Ortga", callback_data="manage_current_shift") # До: ⬅️ Назад
    builder.adjust(1)

    await callback.message.edit_text(res_text, reply_markup=builder.as_markup(), parse_mode="Markdown")


# 3. Само удаление
@router.callback_query(F.data.startswith("del_kg_curr:"))
async def delete_kg_curr(callback: types.CallbackQuery, session: AsyncSession):
    kg_id = int(callback.data.split(":")[1])
    user = await requests.get_user(session, callback.from_user.id)
    shift = await requests.get_active_shift(session, user.id)

    await requests.delete_kg_from_active_shift(session, shift.id, kg_id)
    await callback.answer("Bog'cha o'chirildi!", show_alert=True) # Садик удален!
    await manage_current(callback, session)  # Возвращаем к списку


# 4. Возврат в петлю (кнопка Назад)
@router.callback_query(F.data == "back_to_loop")
async def back_to_loop(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Keyingi qadam nima?",
        reply_markup=get_loop_kb()  # Твоя функция из inline.py
    ) # Что делаем дальше?


# Обработка инлайн-кнопки "Завершить смену" из петли
@router.callback_query(F.data == "go_to_close_shift")
async def inline_close_shift(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    # Передаем callback.from_user.id явно, чтобы не было ошибки NoneType
    await close_shift_start(callback.message, state, session, manual_user_id=callback.from_user.id)
    await callback.answer()


# Этот хендлер мы уже создавали, просто добавим возврат в петлю в конце
@router.callback_query(F.data.startswith("update_date_to:"))
async def finalize_update_date(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    date_type = callback.data.split(":")[1]
    new_date = datetime.now() if date_type == "today" else datetime.now() - timedelta(days=1)

    user = await requests.get_user(session, callback.from_user.id)
    shift = await requests.get_active_shift(session, user.id)

    # Обновляем в базе
    await requests.update_shift_date(session, shift.id, new_date)

    await callback.answer(f"Дата изменена на {new_date.strftime('%d.%m')}", show_alert=True)

    # Возвращаем его к кнопкам "петли"
    await callback.message.edit_text(
        f"✅ Дата всей смены изменена на **{new_date.strftime('%d.%m.%Y')}**ga o'zgartirildi.\n"
        f"Barcha kiritilgan mahsulotlar ushbu sana bilan saqlandi.\n\n"
        f"Keyingi qadam nima?",
        reply_markup=get_loop_kb(),  # Та самая клавиатура с новой кнопкой
        parse_mode="Markdown"
    )
    #f"✅ Дата всей смены изменена на **{new_date.strftime('%d.%m.%Y')}**.\n"
    #    f"Все введенные товары сохранены под этим числом.\n\n"
    #    f"Что делаем дальше?"


# 1. Показываем выбор даты
@router.callback_query(F.data == "change_shift_date_start")
async def change_date_request(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    today = datetime.now().strftime("%d.%m")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%d.%m")

    builder.button(text=f"📅 Bugun ({today})", callback_data="apply_new_date:today") # 📅 Сегодня
    builder.button(text=f"📅 Kecha ({yesterday})", callback_data="apply_new_date:yesterday") # 📅 Вчера
    builder.button(text="⬅️ Ortga", callback_data="back_to_loop") # ⬅️ Назад
    builder.adjust(1)

    await callback.message.edit_text(
        "Sanada adashtingizmi? Ushbu smena uchun to'g'ri sanani tanlang.\n"
        "**Kiritilgan barcha bog'chalar saqlanib qoladi!**",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    # "Вы ошиблись датой? Выберите правильную дату для этой смены.\n"
    #         "**Все введенные садики сохранятся!**"


# 2. Применяем новую дату
@router.callback_query(F.data.startswith("apply_new_date:"))
async def apply_date_fix(callback: types.CallbackQuery, session: AsyncSession):
    date_type = callback.data.split(":")[1]

    # Делаем дату "чистой" (00:00:00)
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    new_date = now if date_type == "today" else now - timedelta(days=1)

    user = await requests.get_user(session, callback.from_user.id)
    shift = await requests.get_active_shift(session, user.id)

    if shift:
        await requests.update_shift_date(session, shift.id, new_date)
        await callback.answer(f"Sana {new_date.strftime('%d.%m')}ga o'zgartirildi", show_alert=True)

        await callback.message.edit_text(
            f"✅ Butun smena sanasi **{new_date.strftime('%d.%m.%Y')}ga o'zgartirildi**.\n"
            "Barcha kiritilgan mahsulotlar ushbu sana bilan saqlandi.\n\n"
            "Keyingi qadam nima?",
            reply_markup=get_loop_kb(),
            parse_mode="Markdown"
        )
        #f"✅ Дата всей смены изменена на **{new_date.strftime('%d.%m.%Y')}**.\n"
        #    "Все данные успешно перенесены.\n\n"
        #    "Что делаем дальше?",
    else:
        await callback.answer("Xato: Faol smena topilmadi", show_alert=True)
        #"Ошибка: Активная смена не найдена"