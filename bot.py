import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import config
from handlers import start, delivery, reports, admin

from database.engine import async_session, init_db
from database.middlewares import DbSessionMiddleware, CheckUserMiddleware


logging.basicConfig(level=logging.INFO)

async def main():
    await init_db()

    bot = Bot(token=config.bot_token.get_secret_value())
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(delivery.router)
    dp.include_router(reports.router)


    dp.update.middleware(DbSessionMiddleware(session_pool=async_session))
    dp.update.middleware(CheckUserMiddleware())

    logging.info('Бот запущен и готов работать')
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен")
