"""
Telegram bot with AI via Google Gemini — Binibit.
"""
import json
import logging
import os
import re
import time
import edge_tts
import httpx
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    ChatMemberHandler,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    filters,
)
import google.generativeai as genai
from stats import init_db, log_message, log_lead, get_stats, stats_command
from binibit_knowledge import BINIBIT_KNOWLEDGE
from digest import digest_scheduler, digest_command
from prompt import SYSTEM_PROMPT, DRAFT_MODE_PROMPT

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "919675687"))

if not TELEGRAM_TOKEN:
    raise RuntimeError("Переменная TELEGRAM_TOKEN пустая или не найдена на Railway!")
if not GEMINI_API_KEY:
    print("⚠️ ВНИМАНИЕ: переменная GEMINI_API_KEY пустая!")
else:
    print(f"Gemini API key загружен, длина: {len(GEMINI_API_KEY)} символов")

genai.configure(api_key=GEMINI_API_KEY)

STYLE_SAMPLES = """"""
MODEL = "gemini-flash-lite-latest"
HISTORY_LIMIT = 10
RATE_LIMIT_MAX = 8
RATE_LIMIT_WINDOW = 60

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

conversation_history = {}
draft_active = set()
_user_msg_times = defaultdict(list)

def is_rate_limited(user_id: int) -> bool:
    now = time.time()
    times = [t for t in _user_msg_times[user_id] if now - t < RATE_LIMIT_WINDOW]
    _user_msg_times[user_id] = times
    if len(times) >= RATE_LIMIT_MAX:
        return True
    _user_msg_times[user_id].append(now)
    return False

DRAFT_TRIGGER = re.compile(r"(объявлен|черновик|анонс|акци[яюие]\b|напиши пост|сделай пост|пост для канала|пост в канал)", re.IGNORECASE)

def is_draft_request(text: str) -> bool:
    return bool(text and DRAFT_TRIGGER.search(text))

RATE_KEYWORDS = ("курс", "цена", "цену", "стоимост", "почём", "почем")
CRYPTO_ALIASES = {
    "btc": "bitcoin", "биткоин": "bitcoin", "биткойн": "bitcoin", "битка": "bitcoin",
    "eth": "ethereum", "эфир": "ethereum", "эфириум": "ethereum",
    "usdt": "tether", "тезер": "tether", "юсдт": "tether",
    "ton": "the-open-network", "тон": "the-open-network",
    "bnb": "binancecoin", "sol": "solana", "солана": "solana",
    "xrp": "ripple", "рипл": "ripple", "doge": "dogecoin", "додж": "dogecoin",
}
FIAT_ALIASES = {"доллар": "USD", "usd": "USD", "евро": "EUR", "eur": "EUR", "юань": "CNY", "cny": "CNY", "тенге": "KZT", "kzt": "KZT"}

BINI_PATTERN = re.compile(r"(?<!\w)(bini|бини)(?!\w)", re.IGNORECASE)
BINI_CONTRACT = "0x445d03f499f1c150615957bb87588fb465fc91cc"

def detect_rate_request(text: str):
    text_lower = text.lower()
    if not any(kw in text_lower for kw in RATE_KEYWORDS):
        return None
    bini_match = BINI_PATTERN.search(text_lower)
    if bini_match:
        return ("bini_unreliable", "bini", bini_match.group(1))
    for alias, coin_id in CRYPTO_ALIASES.items():
        if alias in text_lower:
            return ("crypto", coin_id, alias)
    for alias, code in FIAT_ALIASES.items():
        if alias in text_lower:
            return ("fiat", code, alias)
    return None

async def fetch_crypto_rate(coin_id: str):
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get("https://api.coingecko.com/api/v3/simple/price", params={"ids": coin_id, "vs_currencies": "usd,rub"})
        r.raise_for_status()
        return r.json().get(coin_id)

async def fetch_fiat_rate(code: str):
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get("https://www.cbr-xml-daily.ru/daily_json.js")
        r.raise_for_status()
        data = r.json()
    valute = data.get("Valute", {}).get(code)
    return valute["Value"] / valute["Nominal"] if valute else None

async def build_rate_note(request):
    kind, key, alias = request
    try:
        if kind == "bini_unreliable":
            return "[Точного курса BINI сейчас нет: источники ненадёжны. Скажи, что не можешь дать цифру, предложи посмотреть в Bini App. Не придумывай цифры.]"
        elif kind == "crypto":
            prices = await fetch_crypto_rate(key)
            if not prices: return None
            return f"[Актуальный курс {alias.upper()}: {prices.get('usd')} USD / {prices.get('rub')} RUB (CoinGecko). Озвучь эти цифры.]"
        else:
            rub_rate = await fetch_fiat_rate(key)
            if rub_rate is None: return None
            return f"[Актуальный курс: 1 {key} = {rub_rate:.2f} RUB (ЦБ РФ). Озвучь эту цифру.]"
    except Exception as e:
        logger.error(f"Rate fetch failed: {type(e).__name__}: {e!r}")
        return None

async def get_rate_note_if_asked(text):
    if not text: return None
    request = detect_rate_request(text)
    return await build_rate_note(request) if request else None

QUICK_HELP_TEXT = "Чем могу помочь:\n\n💱 Скажи «курс биткоина» / «курс BINI»\n🔐 Спроси «как пройти верификацию»\n📈 Спроси «что такое стейкинг»\n🎤 Можно голосом\n📎 Можно скриншот\n\nО чём хочешь узнать?"

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💱 Курс BINI", callback_data="q_rate_bini"), InlineKeyboardButton("💱 Курс BTC", callback_data="q_rate_btc")],
        [InlineKeyboardButton("📝 Регистрация", callback_data="q_how_register"), InlineKeyboardButton("🔐 Верификация", callback_data="q_how_kyc")],
        [InlineKeyboardButton("💰 Стейкинг", callback_data="q_staking"), InlineKeyboardButton("🤝 Партнёрка", callback_data="q_referral")],
        [InlineKeyboardButton("❓ Все возможности", callback_data="q_help")],
    ])

QUICK_QUERIES = {
    "q_rate_bini": "Какой сейчас курс BINI?", "q_rate_btc": "Какой сейчас курс биткоина?",
    "q_how_register": "Как зарегистрироваться на Binibit?", "q_how_kyc": "Как пройти верификацию на Binibit?",
    "q_staking": "Расскажи коротко про стейкинг на Binibit.", "q_referral": "Как работает партнёрская программа Binibit?",
}

CHATS_FILE = "known_chats.json"
known_chats = {}
def load_chats():
    global known_chats
    try:
        with open(CHATS_FILE, "r", encoding="utf-8") as f: known_chats = json.load(f)
    except: known_chats = {}
def save_chats():
    try:
        with open(CHATS_FILE, "w", encoding="utf-8") as f: json.dump(known_chats, f, ensure_ascii=False)
    except Exception as e: logger.error(f"save_chats failed: {e!r}")

def remember_chat(chat, is_admin=None):
    key = str(chat.id)
    old = known_chats.get(key, {})
    known_chats[key] = {"title": chat.title or old.get("title") or "(без названия)", "type": chat.type, "admin": old.get("admin") if is_admin is None else is_admin, "seen": int(time.time())}

async def track_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat and chat.type in ("group", "supergroup", "channel"):
        is_new = str(chat.id) not in known_chats
        remember_chat(chat)
        if is_new: save_chats()

async def track_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    event = update.my_chat_member
    if not event or event.chat.type not in ("group", "supergroup", "channel"): return
    status = event.new_chat_member.status
    if status in ("left", "kicked"): known_chats.pop(str(event.chat.id), None)
    else: remember_chat(event.chat, is_admin=(status == "administrator"))
    save_chats()

async def chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or update.message.chat.type != "private": return
    if not known_chats: return await update.message.reply_text("Пока нет чатов.")
    type_names = {"group": "группа", "supergroup": "чат", "channel": "канал"}
    lines = [f"• {i['title']} — {type_names.get(i['type'], i['type'])}" for i in sorted(known_chats.values(), key=lambda x: x['title'].lower())]
    text = f"Чатов: {len(lines)}\n\n" + "\n".join(lines)
    for i in range(0, len(text), 4000): await update.message.reply_text(text[i:i + 4000])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversation_history[update.effective_user.id] = []
    draft_active.discard(update.effective_user.id)
    await update.message.reply_text("Привет! 👋 Я AI-помощник Binibit.\nСпроси что угодно текстом, голосом или скриншотом.\n\nБыстрые кнопки:", reply_markup=main_menu_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(QUICK_HELP_TEXT, reply_markup=main_menu_keyboard())

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversation_history[update.effective_user.id] = []
    draft_active.discard(update.effective_user.id)
    await update.message.reply_text("История очищена.")

async def post_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or update.message.chat.type != "private": return
    draft_active.add(update.effective_user.id)
    await update.message.reply_text("Режим черновиков включён ✍️ Пришли задачу и условия. /chat — выйти.")

async def chat_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or update.message.chat.type != "private": return
    draft_active.discard(update.effective_user.id)
    await update.message.reply_text("Обычный режим включён 💬")

async def on_quick_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "q_help": return await query.message.reply_text(QUICK_HELP_TEXT, reply_markup=main_menu_keyboard())
    prompt = QUICK_QUERIES.get(query.data)
    if not prompt: return
    user_id = query.from_user.id
    if is_rate_limited(user_id): return await query.message.reply_text("Секунду, слишком много запросов 🙂")
    try: log_message(user_id, query.from_user.username, f"[кнопка] {prompt}")
    except: pass
    rate_note = await get_rate_note_if_asked(prompt)
    await _run_ai(user_id, query.from_user.first_name or "друг", prompt, update.update_id, False, f"{prompt}\n\n{rate_note}" if rate_note else None, False, query.message)

def build_gemini_history(history):
    return [{"role": "model" if m["role"] == "assistant" else "user", "parts": [m["content"]]} for m in history]

def is_owner_private(update: Update) -> bool:
    return update.effective_user.id == OWNER_ID and update.message.chat.type == "private"

async def _run_ai(user_id, user_name, user_text, update_id, send_as_voice=False, model_input_text=None, draft_mode=False, reply_to=None):
    if user_id not in conversation_history: conversation_history[user_id] = []
    conversation_history[user_id].append({"role": "user", "content": user_text})
    try:
        if draft_mode: send_as_voice = False
        system_text = SYSTEM_PROMPT.format(user_name=user_name)
        if draft_mode: system_text += DRAFT_MODE_PROMPT + ("\nОБРАЗЦЫ СТИЛЯ:\n" + STYLE_SAMPLES if STYLE_SAMPLES.strip() else "")
        model = genai.GenerativeModel(model_name=MODEL, system_instruction=system_text)
        g_history = build_gemini_history(conversation_history[user_id])
        if model_input_text: g_history[-1]["parts"] = [model_input_text]
        response = model.generate_content(g_history, generation_config=genai.types.GenerationConfig(max_output_tokens=2000 if draft_mode else 800))
        reply_text = response.text
        conversation_history[user_id].append({"role": "assistant", "content": reply_text})
        conversation_history[user_id] = conversation_history[user_id][-HISTORY_LIMIT:]
        if send_as_voice:
            audio_path = f"answer_{user_id}_{update_id}.mp3"
            clean_text = re.sub(r'[^\w\s,?!.\-:;—"\'()А-Яа-яЁё]', '', re.sub(r'(\d)/(\d)', r'\1 \2', reply_text))
            tts = edge_tts.Communicate(clean_text, voice="ru-RU-DmitryNeural")
            await tts.save(audio_path)
            try:
                with open(audio_path, "rb") as f:
                    if reply_to: await reply_to.reply_voice(voice=f)
            except BadRequest as e:
                if "voice_messages_forbidden" in str(e).lower() and reply_to: await reply_to.reply_text(reply_text)
            finally:
                if os.path.exists(audio_path): os.remove(audio_path)
        else:
            if reply_to: await reply_to.reply_text(reply_text)
    except Exception as e:
        logger.error(f"Error: {type(e).__name__}: {e!r}")
        if reply_to:
            try: await reply_to.reply_text("Ошибка ИИ. Попробуйте позже.")
            except: pass

async def process_ai_response(user_id, user_name, user_text, update, context, send_as_voice=False, model_input_text=None, draft_mode=False):
    try: await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice" if send_as_voice else "typing")
    except: pass
    await _run_ai(user_id, user_name, user_text, update.update_id, send_as_voice, model_input_text, draft_mode, update.message)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, user_id = update.message, update.effective_user.id
    user_text = message.text or ""
    if is_rate_limited(user_id): return await message.reply_text("Секунду, слишком много сообщений 🙂")
    try: log_message(user_id, update.effective_user.username, user_text)
    except: pass
    try: log_lead(user_id, update.effective_user.username, update.effective_user.first_name, user_text)
    except: pass
    is_private = message.chat.type == "private"
    is_mentioned = context.bot.username and f"@{context.bot.username}" in user_text
    is_reply = message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.id == context.bot.id
    if not (is_private or is_mentioned or is_reply): return
    draft_mode = is_owner_private(update) and (user_id in draft_active or (is_draft_request(user_text) and draft_active.add(user_id) is None))
    rate_note = await get_rate_note_if_asked(user_text)
    await process_ai_response(user_id, update.effective_user.first_name or "друг", user_text, update, context, False, f"{user_text}\n\n{rate_note}" if rate_note else None, draft_mode)

async def transcribe_voice(voice_path):
    with open(voice_path, "rb") as f: audio_bytes = f.read()
    response = genai.GenerativeModel(model_name=MODEL).generate_content(["Расшифруй голосовое на русском. Верни только текст.", {"mime_type": "audio/ogg", "data": audio_bytes}])
    return response.text.strip()

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, user_id = update.message, update.effective_user.id
    if message.chat.type != "private": return
    voice_path = f"voice_{user_id}_{message.message_id}.ogg"
    try:
        voice_file = await context.bot.get_file(message.voice.file_id)
        await voice_file.download_to_drive(voice_path)
        user_text = await transcribe_voice(voice_path)
        if not user_text: return await message.reply_text("Не удалось разобрать.")
        try: log_message(user_id, update.effective_user.username, f"[Голос]: {user_text}")
        except: pass
        try: log_lead(user_id, update.effective_user.username, update.effective_user.first_name, user_text)
        except: pass
        draft_mode = is_owner_private(update) and (user_id in draft_active or (is_draft_request(user_text) and draft_active.add(user_id) is None))
        rate_note = await get_rate_note_if_asked(user_text)
        await process_ai_response(user_id, update.effective_user.first_name or "друг", user_text, update, context, True, f"{user_text}\n\n{rate_note}" if rate_note else None, draft_mode)
    except Exception as e:
        logger.error(f"Voice Error: {e}")
        await message.reply_text("Ошибка распознавания.")
    finally:
        if os.path.exists(voice_path): os.remove(voice_path)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, user_id = update.message, update.effective_user.id
    if message.chat.type != "private": return
    if is_rate_limited(user_id): return await message.reply_text("Секунду, слишком много запросов 🙂")
    try:
        photo = message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        img_bytes = await file.download_as_bytearray()
        prompt = message.caption or "Что на этом скриншоте? Ответь на вопрос, если он есть, или опиши суть."
        response = genai.GenerativeModel(model_name=MODEL).generate_content([prompt, {"mime_type": "image/jpeg", "data": img_bytes}])
        await message.reply_text(response.text)
    except Exception as e:
        logger.error(f"Photo Error: {e}")
        await message.reply_text("Не удалось прочитать картинку.")

async def _post_init(app):
    app.create_task(digest_scheduler(app.bot))

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(_post_init).build()
    init_db()
    load_chats()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("post", post_mode))
    app.add_handler(CommandHandler("chat", chat_mode))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("chats", chats_command))
    app.add_handler(CommandHandler("digest", digest_command))
    app.add_handler(CallbackQueryHandler(on_quick_button))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, track_chat), group=-1)
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POSTS, track_chat), group=-1)
    app.add_handler(ChatMemberHandler(track_membership, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    print("Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
