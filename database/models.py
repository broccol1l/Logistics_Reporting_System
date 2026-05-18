from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, BigInteger, DateTime, func
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'

    id = Column(BigInteger, primary_key=True)
    full_name = Column(String)
    is_admin = Column(Boolean, default=False)
    phone = Column(String)

    is_blocked = Column(Boolean, default=False)
    is_visible_in_admin = Column(Boolean, default=True)

    shifts = relationship("Shift", back_populates="driver")


class Kindergarten(Base):
    __tablename__ = 'kindergartens'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    is_active = Column(Boolean, default=True)

    deliveries = relationship("Delivery", back_populates="kindergarten")


class Product(Base):
    __tablename__ = 'products'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    unit = Column(String, default="кг")
    price_sadik = Column(Float, default=0.0)
    price_zakup = Column(Float, default=0.0)

    is_active = Column(Boolean, default=True)


class Shift(Base):
    __tablename__ = 'shifts'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id'))
    opened_at = Column(DateTime, default=func.now())
    closed_at = Column(DateTime, nullable=True)
    is_closed = Column(Boolean, default=False)
    fuel_expense = Column(Float, default=0.0)

    other_expenses = Column(Float, default=0.0)
    other_expenses_comment = Column(String, nullable=True)

    driver = relationship("User", back_populates="shifts")
    deliveries = relationship("Delivery", back_populates="shift")


class Delivery(Base):
    __tablename__ = 'deliveries'

    id = Column(Integer, primary_key=True)
    shift_id = Column(Integer, ForeignKey('shifts.id'))
    product_id = Column(Integer, ForeignKey('products.id'))
    kindergarten_id = Column(Integer, ForeignKey('kindergartens.id'))

    weight_plan = Column(Float)
    weight_fact = Column(Float)

    p_sadik_fact = Column(Float)
    p_zakup_fact = Column(Float)

    shift = relationship("Shift", back_populates="deliveries")
    product = relationship("Product")
    kindergarten = relationship("Kindergarten", back_populates="deliveries")

    @property
    def total_price_sadik(self):
        r"""$$Total = weight\_fact \times p\_sadik\_fact$$"""  # Добавили r в начале
        return round(self.weight_fact * self.p_sadik_fact, 2)

    @property
    def total_cost_zakup(self):
        r"""$$Cost = weight\_fact \times p\_zakup\_fact$$"""  # И здесь тоже
        return round(self.weight_fact * self.p_zakup_fact, 2)

    @property
    def net_profit(self):
        """Чистая прибыль"""
        return round(self.total_price_sadik - self.total_cost_zakup, 2)

    @property
    def diff_text(self) -> str:
        val = round(self.weight_plan - self.weight_fact, 2)
        unit = self.product.unit if self.product else "ед."
        if val > 0:
            return f"⚠️ Недостача {val} {unit}"
        return f"✅ Норма ({unit})"