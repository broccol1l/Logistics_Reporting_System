from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, delete, update
from database.models import User, Delivery, Shift, Product, Kindergarten
from sqlalchemy.orm import selectinload

# --- РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ---
async def get_user(session: AsyncSession, tg_id: int):
    return await session.get(User, tg_id)


async def add_user(session: AsyncSession, tg_id: int, full_name: str, phone: str):
    user = User(
        id=tg_id,
        full_name=full_name,
        phone=phone
    )
    session.add(user)
    await session.commit()
    return user


# --- РАБОТА С САДИКАМИ (НОВОЕ) ---
async def get_active_kindergartens(session: AsyncSession):
    query = select(Kindergarten).where(Kindergarten.is_active == True).order_by(Kindergarten.name)
    result = await session.execute(query)
    return result.scalars().all()


async def add_kindergarten(session: AsyncSession, name: str):
    new_kg = Kindergarten(name=name)
    session.add(new_kg)
    await session.commit()
    return new_kg


# --- РАБОТА С ТОВАРАМИ ---
async def get_all_products(session: AsyncSession):
    query = select(Product).where(Product.is_active == True).order_by(Product.name)
    result = await session.execute(query)
    return result.scalars().all()


# --- РАБОТА СО СМЕНАМИ ---
async def get_or_create_shift(session: AsyncSession, user_id: int):
    query = select(Shift).where(
        and_(Shift.user_id == user_id, Shift.is_closed == False)
    )
    result = await session.execute(query)
    shift = result.scalar_one_or_none()

    if not shift:
        shift = Shift(user_id=user_id)
        session.add(shift)
        await session.commit()
        await session.refresh(shift)
    return shift


# --- ОБНОВЛЕННАЯ ОТГРУЗКА ---
async def add_delivery(session: AsyncSession, shift_id: int, product_id: int,
                       kindergarten_id: int, weight_plan: float, weight_fact: float):
    product = await session.get(Product, product_id)

    new_delivery = Delivery(
        shift_id=shift_id,
        product_id=product_id,
        kindergarten_id=kindergarten_id,
        weight_plan=weight_plan,
        weight_fact=weight_fact,
        p_sadik_fact=product.price_sadik,
        p_zakup_fact=product.price_zakup
    )

    session.add(new_delivery)
    await session.commit()
    await session.refresh(new_delivery)
    return new_delivery

from datetime import datetime

async def close_shift(session: AsyncSession, shift_id: int, fuel_amount: float, other_amount: float = 0.0,
                      other_comment: str = ""):
    shift = await session.get(Shift, shift_id)
    if shift:
        shift.fuel_expense = fuel_amount
        shift.other_expenses = other_amount
        shift.other_expenses_comment = other_comment

        shift.is_closed = True
        shift.closed_at = datetime.now()
        await session.commit()
        return shift
    return None


async def get_shift_deliveries(session: AsyncSession, shift_id: int):
    query = select(Delivery).where(
        Delivery.shift_id == shift_id
    ).options(
        selectinload(Delivery.product),
        selectinload(Delivery.kindergarten)
    )
    result = await session.execute(query)
    return result.scalars().all()


# --- ДЛЯ АРХИВА ОТЧЕТОВ ---

async def get_user_shifts(session: AsyncSession, user_id: int, limit: int = 5, offset: int = 0):
    query = (
        select(
            Shift.id,
            Shift.opened_at,
            Shift.closed_at,
            Shift.fuel_expense,
            (func.sum(Delivery.weight_fact * Delivery.p_sadik_fact) - func.coalesce(Shift.fuel_expense, 0)).label('total_sum')
        )
        .join(Delivery, Delivery.shift_id == Shift.id)
        .where(Shift.user_id == user_id, Shift.is_closed == True)
        .group_by(Shift.id, Shift.opened_at, Shift.closed_at, Shift.fuel_expense)
        .order_by(Shift.opened_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(query)
    return result.all()

async def delete_shift_full(session: AsyncSession, shift_id: int):
    await session.execute(delete(Delivery).where(Delivery.shift_id == shift_id))
    await session.execute(delete(Shift).where(Shift.id == shift_id))
    await session.commit()

async def delete_kg_from_active_shift(session: AsyncSession, shift_id: int, kg_id: int):
    await session.execute(
        delete(Delivery).where(Delivery.shift_id == shift_id, Delivery.kindergarten_id == kg_id)
    )
    await session.commit()

async def get_kg_deliveries_in_shift(session: AsyncSession, shift_id: int, kg_id: int):
    query = (
        select(Delivery)
        .where(Delivery.shift_id == shift_id, Delivery.kindergarten_id == kg_id)
        .options(selectinload(Delivery.product))
    )
    result = await session.execute(query)
    return result.scalars().all()

async def get_active_shift(session: AsyncSession, user_id: int):
    query = select(Shift).where(Shift.user_id == user_id, Shift.is_closed == False).order_by(Shift.id.desc())
    result = await session.execute(query)
    return result.scalars().first()

async def create_shift_with_date(session: AsyncSession, user_id: int, date: datetime):
    new_shift = Shift(
        user_id=user_id,
        opened_at=date,
        is_closed=False
    )
    session.add(new_shift)
    await session.commit()
    return new_shift

async def get_shift_by_id(session: AsyncSession, shift_id: int):
    return await session.get(Shift, shift_id)

async def get_all_kindergartens(session: AsyncSession):
    result = await session.execute(select(Kindergarten).where(Kindergarten.is_active == True))
    return result.scalars().all()

from sqlalchemy import update

async def update_shift_date(session: AsyncSession, shift_id: int, new_date: datetime):
    await session.execute(
        update(Shift).where(Shift.id == shift_id).values(opened_at=new_date)
    )
    await session.commit()

async def unclose_shift(session: AsyncSession, shift_id: int):
    await session.execute(
        update(Shift).where(Shift.id == shift_id).values(is_closed=False)
    )
    await session.commit()


async def get_shift_full_details(session: AsyncSession, shift_id: int):
    query = (
        select(Shift)
        .options(
            selectinload(Shift.driver),
            selectinload(Shift.deliveries).selectinload(Delivery.product),
            selectinload(Shift.deliveries).selectinload(Delivery.kindergarten)
        )
        .where(Shift.id == shift_id)
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()


# АНАЛИТИКА
async def get_dashboard_stats(session: AsyncSession, start_date: datetime, end_date: datetime):
    query = select(
        Shift.id,
        Shift.fuel_expense,
        Shift.other_expenses,
        func.sum(Delivery.weight_fact * Delivery.p_sadik_fact).label("revenue"),
        func.sum(Delivery.weight_fact * Delivery.p_zakup_fact).label("cost")
    ).join(Delivery, Delivery.shift_id == Shift.id).where(
        Shift.opened_at >= start_date,
        Shift.opened_at <= end_date,
        Shift.is_closed == True
    ).group_by(Shift.id, Shift.fuel_expense, Shift.other_expenses)

    result = await session.execute(query)
    rows = result.all()

    total_revenue = 0.0
    total_cost = 0.0
    total_fuel = 0.0
    total_other = 0.0

    for row in rows:
        total_revenue += row.revenue or 0.0
        total_cost += row.cost or 0.0
        total_fuel += row.fuel_expense or 0.0
        total_other += row.other_expenses or 0.0

    net_profit = total_revenue - total_cost - total_fuel - total_other

    return {
        "revenue": total_revenue,
        "cost": total_cost,
        "fuel": total_fuel,
        "other_exp": total_other,
        "profit": net_profit
    }

async def get_drivers_performance(session: AsyncSession, start_date: datetime, end_date: datetime):
    query = select(
        User.id,
        User.full_name,
        Shift.id.label("shift_id"),
        Shift.fuel_expense,
        func.sum(Delivery.weight_fact * Delivery.p_sadik_fact).label("revenue"),
        func.sum(Delivery.weight_fact * Delivery.p_zakup_fact).label("cost")
    ).join(Shift, Delivery.shift_id == Shift.id)\
     .join(User, Shift.user_id == User.id)\
     .where(
        Shift.opened_at >= start_date,
        Shift.opened_at <= end_date,
        Shift.is_closed == True
    ).group_by(User.id, User.full_name, Shift.id, Shift.fuel_expense)

    result = await session.execute(query)
    rows = result.all()

    drivers_dict = {}
    for row in rows:
        u_id = row.id
        if u_id not in drivers_dict:
            drivers_dict[u_id] = {
                "id": u_id,
                "name": row.full_name,
                "revenue": 0.0,
                "cost": 0.0,
                "fuel": 0.0
            }
        drivers_dict[u_id]["revenue"] += row.revenue or 0.0
        drivers_dict[u_id]["cost"] += row.cost or 0.0
        drivers_dict[u_id]["fuel"] += row.fuel_expense or 0.0

    drivers_stats = []
    for d in drivers_dict.values():
        profit = d["revenue"] - d["cost"] - d["fuel"]
        drivers_stats.append({
            "id": d["id"],
            "name": d["name"],
            "profit": profit
        })

    return sorted(drivers_stats, key=lambda x: x['profit'], reverse=True)

async def get_all_deliveries_for_export(session: AsyncSession, start_date: datetime = None, end_date: datetime = None):
    query = select(
        Shift.id.label("shift_id"),
        Shift.opened_at.label("Дата"),
        User.full_name.label("Водитель"),
        Kindergarten.name.label("Садик"),
        Product.name.label("Товар"),
        Product.unit.label("Ед_изм"),
        Delivery.weight_plan.label("План"),
        Delivery.weight_fact.label("Факт"),
        Delivery.p_sadik_fact.label("Цена_Садик"),
        Delivery.p_zakup_fact.label("Цена_Закуп"),
        Shift.fuel_expense.label("Бензин_Смены"),
        Shift.other_expenses.label("Другие_Расходы"),
        Shift.other_expenses_comment.label("Комментарий_Расходов"),
        (Delivery.weight_fact * Delivery.p_sadik_fact).label("Выручка"),
        (Delivery.weight_fact * Delivery.p_zakup_fact).label("Закуп_сумма")
    ).join(Delivery.shift).join(Delivery.product).join(Delivery.kindergarten).join(Shift.driver).where(
        Shift.is_closed == True
    )

    if start_date and end_date:
        query = query.where(Shift.opened_at >= start_date, Shift.opened_at <= end_date)

    query = query.order_by(Shift.opened_at.desc())

    result = await session.execute(query)
    return [dict(row._mapping) for row in result.all()]


async def get_deliveries_by_period(session: AsyncSession, start_date: datetime, end_date: datetime):
    query = select(
        Shift.opened_at.label("date"),
        User.full_name.label("driver"),
        Kindergarten.name.label("kg"),
        Product.name.label("product"),
        Product.unit.label("unit"),
        Delivery.weight_fact.label("weight"),
        Delivery.p_sadik_fact.label("price"),
        (Delivery.weight_fact * Delivery.p_sadik_fact).label("total"),
        Shift.fuel_expense.label("fuel"),
        Shift.other_expenses.label("other_exp"),
        Shift.other_expenses_comment.label("other_comment")
    ).join(Delivery.shift).join(Delivery.product).join(Delivery.kindergarten).join(Shift.driver).where(
        Shift.opened_at >= start_date,
        Shift.opened_at <= end_date,
        Shift.is_closed == True
    ).order_by(Shift.opened_at.asc())

    result = await session.execute(query)
    return result.all()