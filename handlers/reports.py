from aiogram import Router, F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.fsm.context import FSMContext

from database import requests
from keyboards import inline


from aiogram.types import FSInputFile
from utils.exporters import create_shift_excel, create_shift_pdf


router = Router()


@router.message(F.text == "📊 Hisobotlarim")  # 📊 Мои отчеты
@router.callback_query(F.data.startswith("rep_page:"))
async def show_my_reports(event: types.Message | types.CallbackQuery, session: AsyncSession):
    page = 0

    if isinstance(event, types.CallbackQuery) and event.data.startswith("rep_page:"):
        try:
            page = int(event.data.split(":")[1])
        except (ValueError, IndexError):
            page = 0

    limit = 5
    offset = page * limit
    user_id = event.from_user.id

    shifts = await requests.get_user_shifts(session, user_id, limit, offset)

    if not shifts and page > 0:
        page = 0
        offset = 0
        shifts = await requests.get_user_shifts(session, user_id, limit, offset)

    if not shifts:
        text = "Sizda hali yopilgan hisobotlar yo'q."
        if isinstance(event, types.CallbackQuery):
            await event.message.edit_text(text)
            await event.answer()
        else:
            await event.answer(text)
        return

    kb = inline.get_reports_paging_kb(shifts, page=page, limit=limit)

    text = f"📂 **Hisobotlar arxivi (стр. {page + 1}):**\nKerakli sanani tanlang."
    #f"📂 **Ваш архив отчетов (стр. {page + 1}):**\nВыберите нужную дату."
    if isinstance(event, types.CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        except Exception:
            pass
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data.startswith("view_rep:"))
async def view_single_report(callback: types.CallbackQuery, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])

    shift = await requests.get_shift_by_id(session, shift_id)
    deliveries = await requests.get_shift_deliveries(session, shift_id)

    if not deliveries or not shift:
        await callback.answer("Ma'lumotlar topilmadi.", show_alert=True)
        return

    report_text = f"📋 **{shift.opened_at.strftime('%d.%m.%Y')} sana uchun hisobot**\n\n"
    total_sum = 0
    for d in deliveries:
        report_text += (
            f"🏫 {d.kindergarten.name}\n"
            f"  ◦ {d.product.name}: {d.weight_fact} {d.product.unit} = {int(d.total_price_sadik):,} so'm\n"
        )
        total_sum += d.total_price_sadik

    fuel = shift.fuel_expense or 0
    other_exp = shift.other_expenses or 0
    other_comment = shift.other_expenses_comment or ""

    total_expenses = fuel + other_exp
    final_amount = total_sum - total_expenses

    report_text += f"\n💰 **UMUMIY TUSHUM: {int(total_sum):,} so'm**"
    report_text += f"\n⛽ Benzin: **-{int(fuel):,} so'm**"

    if other_exp > 0:
        comment_str = f" ({other_comment})" if other_comment else ""
        report_text += f"\n🛠 Boshqa xarajatlar: **-{int(other_exp):,} so'm**{comment_str}"

    report_text += "\n───────────────────"
    report_text += f"\n💵 **TOPSHIRILADIGAN JAMI SUMMA: {int(final_amount):,} so'm**"

    kb = inline.get_report_details_kb(shift_id)
    await callback.message.edit_text(report_text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data.startswith("del_rep:"))
async def delete_report_final(callback: types.CallbackQuery, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])
    await requests.delete_shift_full(session, shift_id)
    await callback.answer("🚨 Hisobot butunlay o'chirildi!", show_alert=True) # 🚨 Отчет полностью удален!

    await show_my_reports(callback, session)


@router.callback_query(F.data.startswith("edit_rep:"))
async def edit_old_report(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    active_shift = await requests.get_active_shift(session, user_id)
    if active_shift and active_shift.id != shift_id:
        await callback.answer("⚠️ Avval joriy smenani yakunlang!", show_alert=True)
        #"⚠️ Сначала завершите текущую смену!"
        return

    await requests.unclose_shift(session, shift_id)

    await state.clear()
    await state.update_data(shift_id=shift_id)

    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Bog'chaga mahsulot qo'shish", callback_data="edit_start_add") # ➕ Добавить товары в садик
    builder.button(text="🔍 Ko'rish / Bog'chani o'chirish", callback_data="manage_current_shift") # 🔍 Просмотр / Удалить садики
    builder.button(text="🗓 Smena sanasini tuzatish", callback_data="change_shift_date_start") # 🗓 Исправить дату смены
    builder.button(text="🏁 Tuzatishlarni yakunlash", callback_data="go_to_close_shift") # 🏁 Завершить правки
    builder.adjust(1)

    await callback.message.edit_text(
        "🛠 **Hisobotni tahrirlash rejimi**\n\n"
        "Nima qilishni xohlaysiz, tanlang:",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    # "🛠 **Режим редактирования отчета**\n\n"
    #         "Выберите, что вы хотите сделать:"
    await callback.answer()


@router.callback_query(F.data == "edit_start_add")
async def edit_start_add(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    from handlers.delivery import show_kindergartens
    await show_kindergartens(callback.message, state, session)


@router.callback_query(F.data.startswith("export_xlsx:"))
async def handle_export_xlsx(callback: types.CallbackQuery, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])
    shift = await requests.get_shift_full_details(session, shift_id)

    if not shift or not shift.deliveries:
        await callback.answer("Ma'lumotlar topilmadi.", show_alert=True) # Данные не найдены"
        return

    await callback.answer("⏳ Excel tayyorlanyapti...") # ⏳ Генерирую Excel...

    user = await requests.get_user(session, callback.from_user.id)

    path = create_shift_excel(shift, is_admin=user.is_admin)
    document = FSInputFile(path)

    await callback.message.answer_document(
        document,
        caption=f"📗 {shift.opened_at.strftime('%d.%m.%Y')} sana uchun Excel-hisobot"
    )
    # 📗 Excel-отчет за {shift.opened_at.strftime('%d.%m.%Y')}


@router.callback_query(F.data.startswith("export_pdf:"))
async def handle_export_pdf(callback: types.CallbackQuery, session: AsyncSession):
    shift_id = int(callback.data.split(":")[1])

    shift = await requests.get_shift_full_details(session, shift_id)

    if not shift or not shift.deliveries:
        await callback.answer("Ushbu hisobot uchun ma'lumotlar topilmadi.", show_alert=True)
        return

    await callback.answer("⏳ PDF-fayl tayyorlanyapti...") # "⏳ Генерирую PDF-файл..."

    user = await requests.get_user(session, callback.from_user.id)

    try:
        pdf_path = create_shift_pdf(shift, is_admin=user.is_admin)

        document = FSInputFile(pdf_path)

        await callback.message.answer_document(
            document=document,
            caption=f"📄 {shift.opened_at.strftime('%d.%m.%Y')} sana uchun PDF-hisobot\nHaydovchi: {shift.driver.full_name}"
        )
        # f"📄 PDF-отчет за {shift.opened_at.strftime('%d.%m.%Y')}\nВодитель: {shift.driver.full_name}"

    except Exception as e:
        await callback.message.answer(f"❌ PDF yaratishda xatolik: {e}") # f"❌ Ошибка при создании PDF: {e}"
        print(f"PDF xatosi: {e}")  # Для отладки в консоли # f"Ошибка PDF: {e}"