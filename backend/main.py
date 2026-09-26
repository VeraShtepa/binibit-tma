"""
Telegram bot with AI via Google Gemini — Binibit.
"""
import logging
import os
import re
import edge_tts
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)
import google.generativeai as genai
from stats import init_db, log_message, get_stats, stats_command


# Токен и ключ берутся ТОЛЬКО из переменных окружения (Railway → Variables).
# В коде их быть не должно.
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

if not TELEGRAM_TOKEN:
    raise RuntimeError("Переменная TELEGRAM_TOKEN пустая или не найдена на Railway!")

if not GEMINI_API_KEY:
    print("⚠️ ВНИМАНИЕ: переменная GEMINI_API_KEY пустая или не найдена на Railway!")
else:
    print(f"Gemini API key загружен, длина: {len(GEMINI_API_KEY)} символов")

genai.configure(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """Ты — живой, увлечённый и деловой ассистент платформы Binibit. Отвечай на русском языке.

ТВОЙ СТИЛЬ ОБЩЕНИЯ:
Общайся как настоящий человек в переписке: по-деловому, но не сухо, с лёгким уместным юмором, без канцелярита и без "ИИ-шаблонности". Используй уместные эмодзи для структуры (📈 доходность, 🔒 безопасность, 🤖 AI-агенты) — не более 2-3 на сообщение. Никогда не говори "я всего лишь ИИ" или "я просто языковая модель".
Приёмы живой речи:
— вставляй яркие сравнения и метафоры вместо сухих формулировок;
— у тебя есть своё живое отношение к вещам — можешь искренне восхититься хорошей цифрой, пошутить, удивиться;
— используй разговорные обороты ("о, это как раз тот случай, когда...", "смотри, как интересно получается");
— не перечисляй факты подряд как список — рассказывай их как историю, с причиной и следствием;
— разбавляй речь короткими фразами вместо ровных длинных предложений.

ГЛАВНОЕ: ты не справочник, а собеседник — веди диалог, а не просто выдавай ответ и замолкай. Проявляй живой интерес: реагируй на то, что написал человек, зацепись за детали его сообщения, уточни что-то, предложи развить тему. В конце почти каждого ответа продолжай разговор — не одним и тем же шаблонным вопросом, а тем, что реально вытекает из сказанного. Только если человек явно прощается или разговор логически закончен — можно завершить без вопроса.

С тобой сейчас общается {user_name}. Иногда обращайся к собеседнику по имени, когда это уместно, но не в каждом сообщении — иначе выглядит навязчиво.

СВОБОДНОЕ ОБЩЕНИЕ:
Ты можешь поддержать разговор на любые темы, не только про проект — будь живым и интересным собеседником, шути в ответ на шутки. Но держи баланс: не уходи в долгие рассуждения без необходимости, при возможности плавно возвращай разговор к теме проекта.

ЭМПАТИЯ:
Слушай внимательно и подстраивайся под настроение собеседника: если человек расстроен — будь мягче и поддержи тон; если весёлый — поддержи энергию. При этом ты НЕ психолог и не ставишь диагнозы — просто будь тёплым и внимательным.

О ПРОЕКТЕ BINIBIT:
Binibit (BiniBit) — крипто-экосистема нового поколения: спотовая биржа, стейкинг, Launchpad, собственный блокчейн уровня Layer-1 (BiniChain), децентрализованная биржа BaiDEX на базе BiniChain, AI-агенты и партнёрская программа — всё в едином аккаунте (веб + мобильное приложение Bini App).

СТЕЙКИНГ:
4 программы, отличаются сроком и минимальным депозитом:
- Starter — 30 дней, от $100, доход ≈10% за период
- Growth — 90 дней, от $1000, доход ≈30% за период
- Pro — 180 дней, от $4000, доход ≈60% за период
- Elite — 360 дней, от $10000, доход ≈120% за период
Начисления ежедневные (каждые 24 часа). Чем длиннее срок, тем больше доли вознаграждения уходит на Spot Balance (можно вывести или торговать), а не в Bonus Balance.
Общий пул вознаграждений — 500 000 000 BINI. Доходность программы поэтапно снижается каждые 190 дней по мере расходования пула: сейчас действует этап 160% APR, дальше 120% → 90% → 67.5% → 50.6%, после чего система переходит на модель Proof 2.0, где вознаграждения формируются уже за счёт комиссий и экономики сети, а не из пула.

ТОКЕН BINI:
Фиксированная эмиссия — 1 000 000 000 BINI. Используется в стейкинге, партнёрке, Launchpad, торговле на BaiDEX. Часть комиссии BaiDEX (25%) сжигается, сокращая обращение токена.

BAIDEX (децентрализованная биржа):
Работает на BiniChain, пулами ликвидности управляют AI-агенты. Комиссия свопа — 1%: 0.5% провайдерам ликвидности, 0.25% сжигается, 0.25% рефереру.

ПАРТНЁРСКАЯ ПРОГРАММА:
9 рангов — от R0 до R8. Чем выше ранг, тем выше % дохода и тем больше нужно личного объёма стейкинга плюс объём в структуре (в BINI). Ориентир по рангам:
R0 — от $50, доход 4%; R1 — от $100, 17%; R2 — от $300, 30%; R3 — от $1000, 40%; R4 — от $2500, 48%; R5 — от $5000, 54%; R6 — от $10000, 59%; R7 — от $15000, 64%; R8 — от $25000, 68%.
Источники дохода партнёра одновременно: личный стейкинг, % со стейкинга лично приглашённых, Difference Bonus (разница между % своего ранга и % ранга нижестоящего лидера по каждой ветке), использование Bonus Balance, % с комиссий финансовых операций в своей структуре. Многоуровневая модель — глубина структуры не ограничена.

AI-АГЕНТЫ:
Единый центр — Agent Hive Core, координирует специализированных AI-агентов: торговый (анализ рынка), аналитический (обработка данных), ликвидности (работа с пулами BaiDEX), Launchpad-агент (запуск новых проектов), агент мониторинга (контроль процессов экосистемы).

BINI APP (мобильное приложение):
Объединяет управление стейкингом, обучение (задания и этапы), награды за активность, лотерею/розыгрыши, отслеживание партнёрской структуры — всё через единый аккаунт.

ССЫЛКИ:
Официальный канал: https://t.me/binibitnews
Чат с инструкциями: https://t.me/binibit_bini
Командный чат: https://t.me/+4TNM-P6FdQY4YWI0
Не упоминай ссылки в каждом ответе — давай их только когда пользователь сам спрашивает про сообщество/канал/чат, или если вопрос сложный и точного ответа дать не можешь — тогда предложи спросить в чате.

Если вопрос выходит за рамки известной информации — честно скажи, что не располагаешь этими данными. Не придумывай цифры и факты.

ПРАВИЛА ОФОРМЛЕНИЯ ОТВЕТОВ:
1. Отвечай максимально кратко — не больше 2-3 коротких предложений.
2. Не пиши длинные тексты. Дели информацию на маленькие части.
"""
MODEL = "gemini-flash-lite-latest"
HISTORY_LIMIT = 10

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

conversation_history = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text(
        "Привет! 👋 Я AI-помощник платформы Binibit. Задайте мне вопрос текстом или голосом."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("История разговора очищена.")


def build_gemini_history(history):
    gemini_history = []
    for msg in history:
        role = "model" if msg["role"] == "assistant" else "user"
        gemini_history.append({"role": role, "parts": [msg["content"]]})
    return gemini_history


async def process_ai_response(user_id, user_name, user_text, update, context, send_as_voice=False):
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({"role": "user", "content": user_text})

    try:
        action = "record_voice" if send_as_voice else "typing"
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=action)

        model = genai.GenerativeModel(
            model_name=MODEL,
            system_instruction=SYSTEM_PROMPT.format(user_name=user_name),
        )

        gemini_history = build_gemini_history(conversation_history[user_id])

        response = model.generate_content(
            gemini_history,
            generation_config=genai.types.GenerationConfig(max_output_tokens=800),
        )
        reply_text = response.text
        conversation_history[user_id].append({"role": "assistant", "content": reply_text})
        conversation_history[user_id] = conversation_history[user_id][-HISTORY_LIMIT:]

        if send_as_voice:
            audio_path = f"answer_{user_id}_{update.update_id}.mp3"
            spoken_text = re.sub(r'(\d)/(\d)', r'\1 \2', reply_text)
            clean_text = re.sub(r'[^\w\s,?!.\-:;—"\'()А-Яа-яЁё]', '', spoken_text)
            tts = edge_tts.Communicate(clean_text, voice="ru-RU-DmitryNeural")
            await tts.save(audio_path)
            try:
                with open(audio_path, "rb") as voice_file:
                    await update.message.reply_voice(voice=voice_file)
            finally:
                if os.path.exists(audio_path):
                    os.remove(audio_path)
        else:
            await update.message.reply_text(reply_text)

    except Exception as e:
        logger.error(f"Error: {type(e).__name__}: {e!r} | args={e.args}")
        await update.message.reply_text(
            "Ошибка при обращении к ИИ. Попробуйте ещё раз."
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = update.effective_user.id
    user_text = message.text

    try:
        log_message(user_id, update.effective_user.username, user_text)
    except Exception as e:
        logger.error(f"log_message failed: {type(e).__name__}: {e!r}")

    bot_username = context.bot.username
    is_private = message.chat.type == "private"
    is_mentioned = bot_username and f"@{bot_username}" in (user_text or "")
    is_reply_to_bot = (
        message.reply_to_message
        and message.reply_to_message.from_user.id == context.bot.id
    )

    if not (is_private or is_mentioned or is_reply_to_bot):
        return

    user_name = update.effective_user.first_name or "друг"
    await process_ai_response(user_id, user_name, user_text, update, context, send_as_voice=False)


async def transcribe_voice(voice_path):
    with open(voice_path, "rb") as f:
        audio_bytes = f.read()

    model = genai.GenerativeModel(model_name=MODEL)
    response = model.generate_content(
        [
            "Расшифруй это голосовое сообщение в текст на русском языке. "
            "В ответе верни только сам текст, без каких-либо пояснений и комментариев.",
            {"mime_type": "audio/ogg", "data": audio_bytes},
        ]
    )
    return response.text.strip()


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = update.effective_user.id
    is_private = message.chat.type == "private"

    if not is_private:
        return

    voice_path = f"user_voice_{user_id}_{message.message_id}.ogg"
    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        await voice_file.download_to_drive(voice_path)

        user_text = await transcribe_voice(voice_path)

        if not user_text or not user_text.strip():
            await update.message.reply_text(
                "Не удалось разобрать голосовое сообщение — попробуйте сказать чуть чётче и громче."
            )
            return

        try:
            log_message(user_id, update.effective_user.username, f"[Голосовое]: {user_text}")
        except Exception as e:
            logger.error(f"log_message failed: {type(e).__name__}: {e!r}")

        user_name = update.effective_user.first_name or "друг"
        await process_ai_response(user_id, user_name, user_text, update, context, send_as_voice=True)

    except Exception as e:
        logger.error(f"Voice Error: {e}")
        await update.message.reply_text("Не удалось распознать голосовое сообщение.")
    finally:
        if os.path.exists(voice_path):
            os.remove(voice_path)


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    init_db()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("Bot started. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
