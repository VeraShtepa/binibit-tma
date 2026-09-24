"""
bot.py — Telegram-бот для Binibit Team Mini App.
Ловит /start и открывает WebApp с реферальным startapp-параметром.
"""

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    WebAppInfo,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    MenuButtonWebApp,
)

# --- Конфиг ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_ТОКЕН_ОТ_BOTFATHER")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://твой-домен/")
BOT_USERNAME = "Assistentvdele_Bot"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("bot")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def _webapp_kb(startapp: str | None = None) -> InlineKeyboardMarkup:
    """Кнопка открытия Mini App. startapp попадает в start_param внутри WebApp."""
    url = f"{WEBAPP_URL}?startapp={startapp}" if startapp else WEBAPP_URL
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🚀 Открыть приложение", web_app=WebAppInfo(url=url))
    ]])


@dp.message(CommandStart(deep_link=True))
async def start_deeplink(message: Message, command: CommandStart):
    """
    /start <payload>
    payload — это user_id пригласившего (его прокидывает main.py в invite_link).
    """
    payload = command.args or ""
    log.info("Deep-link /start | user_id=%s payload=%s", message.from_user.id, payload)

    await message.answer(
        "Привет! Ты пришёл по приглашению. Жми кнопку ниже 👇",
        reply_markup=_webapp_kb(payload or None),
    )


@dp.message(CommandStart())
async def start_plain(message: Message):
    """/start без параметров — пользователь пришёл сам."""
    log.info("Plain /start | user_id=%s", message.from_user.id)
    await message.answer(
        "Привет! Это Binibit Team. Жми кнопку ниже, чтобы открыть приложение 👇",
        reply_markup=_webapp_kb(),
    )


@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "Команды:\n"
        "/start — открыть приложение\n"
        "/help — справка"
    )


async def on_startup():
    """Ставим кнопку меню (слева от поля ввода), чтобы Mini App был всегда под рукой."""
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Binibit Team",
                web_app=WebAppInfo(url=WEBAPP_URL),
            )
        )
        me = await bot.get_me()
        log.info("Bot @%s started | WebApp=%s", me.username, WEBAPP_URL)
    except Exception:
        log.exception("Не удалось поставить menu button")


async def main():
    await on_startup()
    log.info("Polling started")
    await dp.start_polling(bot, drop_pending_updates=False)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot stopped")
