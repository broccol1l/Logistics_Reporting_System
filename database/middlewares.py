from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker

class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, session_pool: async_sessionmaker):
        self.session_pool = session_pool

    async def __call__(self, handler, event, data):
        async with self.session_pool() as session:
            data['session'] = session
            return await handler(event, data)

class CheckUserMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:
        user_tg = data.get("event_from_user")

        if not user_tg:
            return await handler(event, data)

        session = data.get('session')
        user_id = user_tg.id

        from database.models import User
        from sqlalchemy import select

        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user and user.is_blocked:
            if data.get("event_chat"):
                from aiogram.types import Message, CallbackQuery
                if isinstance(event.event, Message):
                    await event.event.answer("🚫 **Доступ закрыт.**\nВы заблокированы администратором.")
                elif isinstance(event.event, CallbackQuery):
                    await event.event.answer("🚫 Доступ закрыт.", show_alert=True)
            return

        data['user'] = user
        return await handler(event, data)