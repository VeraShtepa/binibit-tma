"""
Планировщик еженедельного дайджеста для владельца.
Запускается из main.py через post_init.
"""
import asyncio
import logging
from datetime import datetime, time as dtime, timezone, timedelta

from telegram import Bot
from telegram.error import TelegramError

from stats import get_weekly_digest, OWNER_ID

logger = logging.getLogger(__name__)

DIGEST_WEEKDAY = 0  # 0 = понедельник
DIGEST_TIME = dtime(hour=10, minute=0, tzinfo=timezone.utc)

def _seconds_until_next_digest() -> float:
    now = datetime.now(timezone.utc)
    days_ahead = DIGEST_WEEKDAY - now.weekday()
    if days_ahead < 0:
        days_ahead += 7
    target = datetime.combine((now + timedelta(days=days_ahead)).date(), DIGEST_TIME)
    if target <= now:
        target += timedelta(days=7)
    return (target - now).total_seconds()

async def digest_scheduler(bot: Bot):
    await asyncio.sleep(15)
    while True:
        try:
            wait = _seconds_until_next_digest()
            logger.info(f"Дайджест: следующая отправка через {wait / 3600:.1f} ч")
            await asyncio.sleep(wait)
            text = get_weekly_digest()
            for i in range(0, len(text), 4000):
                await bot.send_message(chat_id=OWNER_ID, text=text[i:i + 4000])
            logger.info("Дайджест отправлен владельцу")
        except TelegramError as e:
            logger.error(f"Дайджест: ошибка Telegram: {e!r}")
        except Exception as e:
            logger.error(f"Дайджест: ошибка: {type(e).__name__}: {e!r}")
        await asyncio.sleep(3600)

async def digest_command(update, context):
    """/digest — прислать дайджест прямо сейчас (только владелец, только в личке)."""
    if update.effective_user.id != OWNER_ID or update.message.chat.type != "private":
        return
    text = get_weekly_digest()
    for i in range(0, len(text), 4000):
        await update.message.reply_text(text[i:i + 4000])
