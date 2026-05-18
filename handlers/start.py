from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from database import requests
from utils.states import Register, EditName
from keyboards.reply import get_register_kb, main_menu_kb

router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext, session: AsyncSession):
    user = await requests.get_user(session, message.from_user.id)

    if user:
        await message.answer(f"Xush kelibsiz, {user.full_name}!", reply_markup=main_menu_kb()) # С возвращением,
    else:
        await message.answer("Assalomu alaykum! Siz tizimdan ro'yxatdan o'tmagansiz.\nIsm va familiyangizni kiriting:")
        # ("Привет! Вы не зарегистрированы в системе.\nВведите ваше Имя и Фамилию:")
        await state.set_state(Register.name)


@router.message(Register.name)
async def reg_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Endi telefon raqamingizni yuboring", reply_markup=get_register_kb())
    # Теперь отправьте свой номер телефона
    await state.set_state(Register.phone)


@router.message(Register.phone, F.contact)
async def reg_phone(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()

    user_phone = message.contact.phone_number

    await requests.add_user(
        session=session,
        tg_id=message.from_user.id,
        full_name=data["name"],
        phone=user_phone
    )

    await state.clear()
    await message.answer(
        f"Ro'yxatdan o'tish yakunlandi!\nIsm: {data['name']}\nTel: {user_phone}",
        reply_markup=main_menu_kb()
    )
    #f"Регистрация завершена!\nИмя: {data['name']}\nТел: {user_phone}"


@router.message(F.text == "📝 Ismni o'zgartirish") # 📝 Изменить имя
async def edit_name_start(message: types.Message, state: FSMContext):
    await message.answer("Yangi ism va familiyangizni kiriting:") # Введите ваше новое Имя и Фамилию:
    await state.set_state(EditName.name)


@router.message(EditName.name)
async def edit_name_finish(message: types.Message, state: FSMContext, session: AsyncSession):
    new_name = message.text

    from sqlalchemy import update
    from database.models import User

    await session.execute(
        update(User).where(User.id == message.from_user.id).values(full_name=new_name)
    )
    await session.commit()

    await state.clear()
    await message.answer(f"✅ Tayyor! Endi sizni shunday chaqiraman: **{new_name}**",
                         reply_markup=main_menu_kb(),
                         parse_mode="Markdown")
    # ✅ Готово! Теперь я буду называть вас: {new_name}