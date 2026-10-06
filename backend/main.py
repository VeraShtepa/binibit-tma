"""
Telegram bot with AI via Google Gemini — Binibit.
+ Режим черновиков объявлений/постов (только для владельца).
"""
import json
import logging
import os
import re
import time
import edge_tts
import httpx
from telegram import Update
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    ChatMemberHandler,
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

# Telegram ID владельца — только ему доступен режим черновиков.
# Можно переопределить переменной OWNER_ID на Railway.
OWNER_ID = int(os.environ.get("OWNER_ID", "919675687"))

if not TELEGRAM_TOKEN:
    raise RuntimeError("Переменная TELEGRAM_TOKEN пустая или не найдена на Railway!")

if not GEMINI_API_KEY:
    print("⚠️ ВНИМАНИЕ: переменная GEMINI_API_KEY пустая или не найдена на Railway!")
else:
    print(f"Gemini API key загружен, длина: {len(GEMINI_API_KEY)} символов")

genai.configure(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """Ты — живой, классный собеседник и помощник платформы Binibit. Отвечай на русском языке.

ТВОЙ ХАРАКТЕР:
Ты не робот и не справочник — ты нормальный человек в переписке, с которым приятно поговорить. Пиши легко, на позитиве, без канцелярита, без сухих протокольных формулировок и без "я всего лишь ИИ" / "я просто языковая модель". У тебя есть чувство юмора — не плоское и не натужное, а живое: неожиданное сравнение, лёгкая ирония, искреннее "ого, круто" там, где это уместно. Не превращай каждый ответ в стендап, но и не бойся пошутить, если собеседник настроен на это.
Пара приёмов, которые делают речь живой:
— яркие сравнения и метафоры вместо сухих формулировок;
— разговорные обороты и лёгкие восклицания;
— короткие фразы вперемешку с обычными — так речь звучит естественнее;
— искренняя реакция на то, что написал человек, а не шаблонное "понял, отвечаю".
Используй уместные эмодзи для структуры (📈 доходность, 🔒 безопасность, 🤖 AI-агенты) — не больше 2-3 на сообщение, не через каждое слово.

ГЛАВНОЕ: ты собеседник, а не автоответчик — веди диалог. Реагируй на детали в сообщении человека, уточняй, предлагай развить тему. В конце почти каждого ответа можно продолжить разговор — но не одним и тем же шаблонным вопросом, а тем, что реально вытекает из сказанного. Если человек явно прощается или разговор закончен — заканчивай без вопроса.

С тобой сейчас общается {user_name}. Иногда обращайся по имени, когда это естественно, но не в каждом сообщении — иначе выглядит навязчиво.

СВОБОДНОЕ ОБЩЕНИЕ:
Можешь поддержать разговор на любые темы, не только про проект — будь интересным собеседником, шути в ответ на шутки. При этом не уходи в долгие рассуждения без нужды и при случае мягко возвращай разговор к теме Binibit.

ЭМПАТИЯ:
Слушай внимательно и подстраивайся под настроение: расстроен человек — будь мягче, весёлый — поддержи энергию. Ты НЕ психолог и не ставишь диагнозы — просто будь тёплым и внимательным.

КУРСЫ ВАЛЮТ И КРИПТЫ (ЖЁСТКОЕ ПРАВИЛО, ВЫШЕ ЛЮБОГО ХАРАКТЕРА И ЮМОРА):
Если пользователь спрашивает курс какой-то валюты или криптовалюты (в том числе BINI), отвечай прямо в сообщении конкретной цифрой — никогда не отправляй его "посмотреть на сайте", в канал или в чат вместо ответа.
Если перед сообщением пользователя тебе передана техническая пометка вида "[Актуальный курс ...]" — в ней реальные свежие данные, полученные автоматически прямо перед твоим ответом. Всегда бери цифры именно оттуда и озвучивай их своими словами.
Если такой пометки нет, а вопрос про курс всё равно есть — значит, свежие данные сейчас получить не удалось.
В этом случае запрещено категорически:
- называть ЛЮБУЮ цифру курса — ни реальную по памяти, ни приблизительную, ни "для примера";
- придумывать причину, почему данных нет ("источники ушли в отпуск", "обновляю базу" и подобное) — это тоже выдумка, даже в шутливой форме;
- продолжать предыдущую шутку или ролевую игру, если внутри неё есть цифра курса.
Вместо этого прямо и без вариантов скажи: "Сейчас не могу посмотреть точный курс — спроси чуть позже" — и больше ничего про цифры в этом ответе. Это правило сильнее, чем твой характер и чувство юмора: шутить можно обо всём, кроме денег и курсов.
Если пользователь сомневается в твоих цифрах или спрашивает, откуда они — отвечай честно и буднично ("беру из открытого источника по курсам криптовалют"), без красивых выдумок вроде "специальных датчиков", "внутренних источников" или подобных историй. Если ты не уверен в источнике — так и скажи.

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
Не упоминай ссылки в каждом ответе и не используй их как замену прямому ответу — давай их только когда пользователь сам спрашивает про сообщество/канал/чат, или если вопрос сложный и точного ответа ты дать не можешь (и это не вопрос про курс — курс см. правило выше).

Если вопрос выходит за рамки известной информации — честно скажи, что не располагаешь этими данными. Не придумывай цифры и факты.

ПРАВИЛА ОФОРМЛЕНИЯ ОТВЕТОВ:
1. Отвечай максимально кратко — не больше 2-3 коротких предложений.
2. Не пиши длинные тексты. Дели информацию на маленькие части.
"""

# ──────────────────────────────────────────────────────────────────
# Режим черновиков (только для владельца)
# ──────────────────────────────────────────────────────────────────

# Сюда можно вставить 1-2 коротких своих поста как образец стиля
# (между тройными кавычками). Пока пусто — бот опирается на правила ниже.
STYLE_SAMPLES = """"""

DRAFT_MODE_PROMPT = """

=== РЕЖИМ ЧЕРНОВИКОВ (ВАЖНО: перекрывает правила оформления выше) ===
Сейчас с тобой общается владелец канала. Он просит подготовить объявление, акцию или пост для канала. Правило про 2-3 предложения здесь НЕ действует: пиши полноценный готовый черновик нужной длины.

СТИЛЬ:
- от первого лица, спокойно, как делятся личным опытом, без хайпа и «золотых гор»
- короткие абзацы, эмодзи умеренно (✔️ 🚀), без крика и капса
- в аналитических постах: вопрос-подводка, затем список возможностей с ✔️, затем оговорка «запуск не гарантирует успех, результат зависит от...»
- всегда честно называй риски: «у любого инструмента есть особенности и риски, решение каждый принимает сам»
- заверши мягким призывом: «если интересно разобраться, пишите мне в личные сообщения, покажу и отвечу на вопросы, без давления»
- не используй фразы «быстрые деньги», «гарантированный доход», «уверенная прибыль»

ПРАВИЛА:
- Условия акции (проценты, суммы, сроки, даты) бери ТОЛЬКО из слов владельца. Если их нет, задай один уточняющий вопрос и ничего не придумывай.
- Цифры доходности из описания проекта выше (проценты стейкинга, APR, ранги) НЕ вставляй в пост, если владелец сам не назвал их в запросе.
- Личный опыт («я проверила вывод», «мне начисляется») пиши только если владелец сам это подтвердил в запросе.
- Не сравнивай с банковскими вкладами, если владелец сам об этом не просил.
- В самом конце черновика отдельной строкой напиши: «Черновик для проверки».
- Если владелец просит поправить («короче», «мягче», «добавь про...») — выдай исправленную версию целиком.
"""

MODEL = "gemini-flash-lite-latest"
HISTORY_LIMIT = 10

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

conversation_history = {}

# Владельцы (по факту один), у которых сейчас включён режим черновиков
draft_active = set()

DRAFT_TRIGGER = re.compile(
    r"(объявлен|черновик|анонс|акци[яюие]\b|напиши пост|сделай пост|пост для канала|пост в канал)",
    re.IGNORECASE,
)


def is_draft_request(text: str) -> bool:
    return bool(text and DRAFT_TRIGGER.search(text))


# ──────────────────────────────────────────────────────────────────
# Курсы валют и крипты в реальном времени
# ──────────────────────────────────────────────────────────────────

RATE_KEYWORDS = ("курс", "цена", "цену", "стоимост", "почём", "почем")

CRYPTO_ALIASES = {
    "btc": "bitcoin", "биткоин": "bitcoin", "биткойн": "bitcoin", "битка": "bitcoin",
    "eth": "ethereum", "эфир": "ethereum", "эфириум": "ethereum",
    "usdt": "tether", "тезер": "tether", "юсдт": "tether",
    "ton": "the-open-network", "тон": "the-open-network",
    "bnb": "binancecoin",
    "sol": "solana", "солана": "solana",
    "xrp": "ripple", "рипл": "ripple",
    "doge": "dogecoin", "додж": "dogecoin",
}

FIAT_ALIASES = {
    "доллар": "USD", "usd": "USD",
    "евро": "EUR", "eur": "EUR",
    "юань": "CNY", "cny": "CNY",
    "тенге": "KZT", "kzt": "KZT",
}

# BINI не торгуется как обычная монета на CoinGecko по id — берём курс
# по адресу контракта токена в сети Ethereum.
BINI_ALIASES = ("bini", "бини", "бинибит", "binibit")
BINI_CONTRACT = "0x445d03f499f1c150615957bb87588fb465fc91cc"


def detect_rate_request(text: str):
    """Ищет в сообщении запрос курса валюты/крипты. Возвращает (kind, key, alias) или None."""
    text_lower = text.lower()
    if not any(kw in text_lower for kw in RATE_KEYWORDS):
        return None

    for alias in BINI_ALIASES:
        if alias in text_lower:
            return ("bini_unreliable", "bini", alias)

    for alias, coin_id in CRYPTO_ALIASES.items():
        if alias in text_lower:
            return ("crypto", coin_id, alias)

    for alias, code in FIAT_ALIASES.items():
        if alias in text_lower:
            return ("fiat", code, alias)

    return None


async def fetch_crypto_rate(coin_id: str):
    """Курс криптовалюты в USD и RUB через CoinGecko (без ключа)."""
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": coin_id, "vs_currencies": "usd,rub"},
        )
        r.raise_for_status()
        data = r.json()
    return data.get(coin_id)


async def fetch_bini_rate():
    """Курс токена BINI (Binibit) в USD через CoinGecko по адресу контракта в Ethereum."""
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(
            f"https://api.coingecko.com/api/v3/simple/token_price/ethereum",
            params={"contract_addresses": BINI_CONTRACT, "vs_currencies": "usd,rub"},
        )
        r.raise_for_status()
        data = r.json()
    return data.get(BINI_CONTRACT.lower())


async def fetch_fiat_rate(code: str):
    """Курс фиатной валюты к рублю через ЦБ РФ (без ключа)."""
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get("https://www.cbr-xml-daily.ru/daily_json.js")
        r.raise_for_status()
        data = r.json()
    valute = data.get("Valute", {}).get(code)
    if not valute:
        return None
    return valute["Value"] / valute["Nominal"]


async def build_rate_note(request):
    """Собирает техническую пометку с реальными цифрами для модели. None, если не вышло получить данные."""
    kind, key, alias = request
    try:
        if kind == "bini_unreliable":
            # У BINI нет надёжного публичного листинга: цена по контракту в Ethereum
            # берётся из малоликвидного пула и сильно расходится с ценой на самой
            # бирже Binibit. Поэтому НЕ отвечаем числом — явно просим модель
            # честно сказать, что точного курса сейчас дать не может.
            return (
                "[Точного курса BINI сейчас нет: автоматические источники по этому "
                "токену ненадёжны и могут сильно отличаться от биржи. Прямо скажи "
                "пользователю, что не можешь дать точную цифру прямо сейчас, и "
                "предложи посмотреть актуальный курс в приложении Bini App или на "
                "бирже Binibit. Не называй никакую цифру и не придумывай источник данных.]"
            )
        elif kind == "crypto":
            prices = await fetch_crypto_rate(key)
            if not prices:
                return None
            usd = prices.get("usd")
            rub = prices.get("rub")
            return (
                f"[Актуальный курс {alias.upper()}: {usd} USD / {rub} RUB "
                f"(источник: CoinGecko). Озвучь эти цифры пользователю прямо в ответе, "
                f"не отправляй на внешние сайты, в канал или чат.]"
            )
        else:
            rub_rate = await fetch_fiat_rate(key)
            if rub_rate is None:
                return None
            return (
                f"[Актуальный курс: 1 {key} = {rub_rate:.2f} RUB (источник: ЦБ РФ). "
                f"Озвучь эту цифру пользователю прямо в ответе, "
                f"не отправляй на внешние сайты, в канал или чат.]"
            )
    except Exception as e:
        logger.error(f"Rate fetch failed: {type(e).__name__}: {e!r}")
        return None


async def get_rate_note_if_asked(text):
    if not text:
        return None
    request = detect_rate_request(text)
    if not request:
        return None
    return await build_rate_note(request)


# ──────────────────────────────────────────────────────────────────
# Реестр чатов: в каких чатах и каналах состоит бот
# ──────────────────────────────────────────────────────────────────

CHATS_FILE = "known_chats.json"
known_chats = {}


def load_chats():
    global known_chats
    try:
        with open(CHATS_FILE, "r", encoding="utf-8") as f:
            known_chats = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        known_chats = {}


def save_chats():
    try:
        with open(CHATS_FILE, "w", encoding="utf-8") as f:
            json.dump(known_chats, f, ensure_ascii=False)
    except Exception as e:
        logger.error(f"save_chats failed: {type(e).__name__}: {e!r}")


def remember_chat(chat, is_admin=None):
    key = str(chat.id)
    old = known_chats.get(key, {})
    known_chats[key] = {
        "title": chat.title or old.get("title") or "(без названия)",
        "type": chat.type,
        "admin": old.get("admin") if is_admin is None else is_admin,
        "seen": int(time.time()),
    }


async def track_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тихо запоминает любой групповой чат или канал, где бот увидел сообщение."""
    chat = update.effective_chat
    if chat and chat.type in ("group", "supergroup", "channel"):
        is_new = str(chat.id) not in known_chats
        remember_chat(chat)
        if is_new:
            save_chats()


async def track_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ловит момент, когда бота добавили, сделали админом или убрали из чата."""
    event = update.my_chat_member
    if not event or event.chat.type not in ("group", "supergroup", "channel"):
        return
    status = event.new_chat_member.status
    if status in ("left", "kicked"):
        known_chats.pop(str(event.chat.id), None)
    else:
        remember_chat(event.chat, is_admin=(status == "administrator"))
    save_chats()


async def chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/chats — список чатов бота (только владелец, только в личке)."""
    if update.effective_user.id != OWNER_ID or update.message.chat.type != "private":
        return
    if not known_chats:
        await update.message.reply_text(
            "Пока не вижу ни одного чата. Список наполняется, когда в чате появляется сообщение "
            "или бота добавляют/делают админом."
        )
        return
    type_names = {"group": "группа", "supergroup": "чат", "channel": "канал"}
    lines = []
    for info in sorted(known_chats.values(), key=lambda i: i["title"].lower()):
        role = "админ" if info.get("admin") else "не админ" if info.get("admin") is False else "?"
        lines.append(f"• {info['title']} — {type_names.get(info['type'], info['type'])}, {role}")
    text = f"Чатов и каналов: {len(lines)}\n\n" + "\n".join(lines)
    for i in range(0, len(text), 4000):
        await update.message.reply_text(text[i:i + 4000])


# ──────────────────────────────────────────────────────────────────
# Обработчики команд
# ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    draft_active.discard(user_id)
    await update.message.reply_text(
        "Привет! 👋 Я AI-помощник платформы Binibit. Задайте мне вопрос текстом или голосом."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    draft_active.discard(user_id)
    await update.message.reply_text("История разговора очищена.")


async def post_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/post — включить режим черновиков (только владелец, только в личке)."""
    user_id = update.effective_user.id
    if user_id != OWNER_ID or update.message.chat.type != "private":
        return  # для всех остальных команды как будто нет
    draft_active.add(user_id)
    await update.message.reply_text(
        "Режим черновиков включён ✍️ Пришли задачу и условия (что за акция, сроки, суммы). "
        "Чтобы вернуться к обычному общению — /chat."
    )


async def chat_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/chat — выключить режим черновиков."""
    user_id = update.effective_user.id
    if user_id != OWNER_ID or update.message.chat.type != "private":
        return
    draft_active.discard(user_id)
    await update.message.reply_text("Обычный режим включён 💬")


def build_gemini_history(history):
    """Переводит нашу историю [{'role': 'user'/'assistant', 'content': ...}]
    в формат, который понимает Gemini: [{'role': 'user'/'model', 'parts': [...]}, ...]"""
    gemini_history = []
    for msg in history:
        role = "model" if msg["role"] == "assistant" else "user"
        gemini_history.append({"role": role, "parts": [msg["content"]]})
    return gemini_history


def is_owner_private(update: Update) -> bool:
    return (
        update.effective_user.id == OWNER_ID
        and update.message.chat.type == "private"
    )


async def process_ai_response(
    user_id, user_name, user_text, update, context,
    send_as_voice=False, model_input_text=None, draft_mode=False,
):
    """Общая функция для генерации ответа через Gemini.
    model_input_text — если задан, именно этот (расширенный) текст уходит модели
    на этот запрос, а в истории диалога остаётся исходное сообщение пользователя.
    draft_mode — режим черновиков (только для владельца): длинный ответ, текстом."""
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({"role": "user", "content": user_text})

    try:
        if draft_mode:
            send_as_voice = False  # черновик всегда текстом, чтобы можно было скопировать

        action = "record_voice" if send_as_voice else "typing"
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=action)

        system_text = SYSTEM_PROMPT.format(user_name=user_name)
        if draft_mode:
            system_text += DRAFT_MODE_PROMPT
            if STYLE_SAMPLES.strip():
                system_text += "\nОБРАЗЦЫ СТИЛЯ:\n" + STYLE_SAMPLES

        model = genai.GenerativeModel(
            model_name=MODEL,
            system_instruction=system_text,
        )

        gemini_history = build_gemini_history(conversation_history[user_id])
        if model_input_text:
            gemini_history[-1]["parts"] = [model_input_text]

        response = model.generate_content(
            gemini_history,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=2000 if draft_mode else 800
            ),
        )
        reply_text = response.text
        conversation_history[user_id].append({"role": "assistant", "content": reply_text})

        # Обрезаем историю уже после добавления обоих сообщений
        conversation_history[user_id] = conversation_history[user_id][-HISTORY_LIMIT:]

        if send_as_voice:
            audio_path = f"answer_{user_id}_{update.update_id}.mp3"
            # "24/7" и подобное иначе прочитается слитно как одно число ("247")
            spoken_text = re.sub(r'(\d)/(\d)', r'\1 \2', reply_text)
            clean_text = re.sub(r'[^\w\s,?!.\-:;—"\'()А-Яа-яЁё]', '', spoken_text)
            tts = edge_tts.Communicate(clean_text, voice="ru-RU-DmitryNeural")
            await tts.save(audio_path)
            try:
                try:
                    with open(audio_path, "rb") as voice_file:
                        await update.message.reply_voice(voice=voice_file)
                except BadRequest as e:
                    if "voice_messages_forbidden" in str(e).lower():
                        # Пользователь запретил в настройках приватности присылать
                        # ему голосовые — просто шлём обычным текстом вместо этого.
                        await update.message.reply_text(reply_text)
                    else:
                        raise
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
        # Ошибка записи статистики не должна обрывать ответ пользователю
        logger.error(f"log_message failed: {type(e).__name__}: {e!r}")

    # --- фильтр: отвечаем только если это личка, или к боту обратились явно ---
    bot_username = context.bot.username
    is_private = message.chat.type == "private"
    is_mentioned = bot_username and f"@{bot_username}" in (user_text or "")
    is_reply_to_bot = (
        message.reply_to_message
        and message.reply_to_message.from_user.id == context.bot.id
    )

    if not (is_private or is_mentioned or is_reply_to_bot):
        return  # в группе бот молчит, если не обратились именно к нему

    user_name = update.effective_user.first_name or "друг"

    # --- режим черновиков: только владелец и только в личке ---
    draft_mode = False
    if is_owner_private(update):
        if is_draft_request(user_text):
            draft_active.add(user_id)
        draft_mode = user_id in draft_active

    rate_note = await get_rate_note_if_asked(user_text)
    model_input_text = f"{user_text}\n\n{rate_note}" if rate_note else None

    await process_ai_response(
        user_id, user_name, user_text, update, context,
        send_as_voice=False, model_input_text=model_input_text,
        draft_mode=draft_mode,
    )


async def transcribe_voice(voice_path):
    """Распознаём голосовое через Gemini (модель понимает аудио напрямую).
    Передаём байты аудио прямо в запрос, без отдельной загрузки файла —
    так работает даже с обычным API-ключом, без специальных прав на File API."""
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
    """Обработка голосовых сообщений"""
    message = update.message
    user_id = update.effective_user.id
    is_private = message.chat.type == "private"

    if not is_private:
        return

    # Уникальное имя файла на каждое сообщение — избегаем коллизий
    # при параллельных голосовых от одного пользователя
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

        # --- режим черновиков и для голосовых владельца ---
        draft_mode = False
        if is_owner_private(update):
            if is_draft_request(user_text):
                draft_active.add(user_id)
            draft_mode = user_id in draft_active

        rate_note = await get_rate_note_if_asked(user_text)
        model_input_text = f"{user_text}\n\n{rate_note}" if rate_note else None

        await process_ai_response(
            user_id, user_name, user_text, update, context,
            send_as_voice=True, model_input_text=model_input_text,
            draft_mode=draft_mode,
        )

    except Exception as e:
        logger.error(f"Voice Error: {e}")
        await update.message.reply_text("Не удалось распознать голосовое сообщение.")
    finally:
        if os.path.exists(voice_path):
            os.remove(voice_path)


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    init_db()
    load_chats()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("post", post_mode))
    app.add_handler(CommandHandler("chat", chat_mode))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("chats", chats_command))
    # Реестр чатов работает в отдельной группе (-1) и не мешает обычным ответам
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, track_chat), group=-1)
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POSTS, track_chat), group=-1)
    app.add_handler(ChatMemberHandler(track_membership, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("Bot started. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
