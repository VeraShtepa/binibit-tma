"""
Статистика сообщений и лидов.
SQLite, файл bot_stats.db.
"""
import os
import re
import time
import sqlite3
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ContextTypes

DB_PATH = os.environ.get("STATS_DB_PATH", "bot_stats.db")

OWNER_ID = int(os.environ.get("OWNER_ID", "919675687"))

LEAD_TRIGGERS = re.compile(
    r"(зарегистр|регистрац|как начать|как войти|вход\b|создать аккаунт|открыть аккаунт|"
    r"верификац|верифик|kyc|паспорт|пройти проверку|подтвердить личность|"
    r"реферальн|рефкод|реф.ссы|пригласительн|"
    r"пополнить|купить bini|купить бини|как купить|депозит|ввести средства|"
    r"вывести|вывод средств|withdraw)",
    re.IGNORECASE,
)


def _conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with _conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                text TEXT,
                created_at INTEGER NOT NULL
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_time ON messages(created_at)")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                topic TEXT NOT NULL,
                trigger_text TEXT,
                created_at INTEGER NOT NULL,
                UNIQUE(user_id, topic)
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_time ON leads(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_topic ON leads(topic)")


# ──────────────────────────────────────────────────────────────────
# Сообщения
# ──────────────────────────────────────────────────────────────────

def log_message(user_id: int, username, text):
    if not text:
        return
    with _conn() as conn:
        conn.execute(
            "INSERT INTO messages (user_id, username, text, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username or "", text[:4000], int(time.time())),
        )


# ──────────────────────────────────────────────────────────────────
# Лиды
# ──────────────────────────────────────────────────────────────────

def _detect_lead_topic(text: str):
    if not text:
        return None
    t = text.lower()
    if not LEAD_TRIGGERS.search(t):
        return None
    if re.search(r"(верификац|верифик|kyc|паспорт|подтвердить личность|пройти проверку)", t):
        return "kyc"
    if re.search(r"(зарегистр|регистрац|как начать|как войти|вход\b|создать аккаунт|открыть аккаунт)", t):
        return "registration"
    if re.search(r"(пополнить|депозит|ввести средства|купить bini|купить бини|как купить)", t):
        return "deposit"
    if re.search(r"(вывести|вывод средств|withdraw)", t):
        return "withdraw"
    if re.search(r"(реферальн|рефкод|реф.ссы|пригласительн)", t):
        return "referral"
    return "other"


def log_lead(user_id: int, username, first_name, text):
    topic = _detect_lead_topic(text or "")
    if not topic:
        return None
    try:
        with _conn() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO leads
                   (user_id, username, first_name, topic, trigger_text, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, username or "", first_name or "", topic, (text or "")[:1000], int(time.time())),
            )
            if cur.rowcount == 0:
                return None
            return topic
    except Exception:
        return None


def get_stats() -> dict:
    now = int(time.time())
    day_ago = now - 86400
    week_ago = now - 7 * 86400
    month_ago = now - 30 * 86400

    with _conn() as conn:
        total_users = conn.execute("SELECT COUNT(DISTINCT user_id) FROM messages").fetchone()[0]
        total_msgs = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        day_users = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM messages WHERE created_at >= ?", (day_ago,)
        ).fetchone()[0]
        day_msgs = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE created_at >= ?", (day_ago,)
        ).fetchone()[0]
        week_users = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM messages WHERE created_at >= ?", (week_ago,)
        ).fetchone()[0]
        week_msgs = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE created_at >= ?", (week_ago,)
        ).fetchone()[0]
        month_users = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM messages WHERE created_at >= ?", (month_ago,)
        ).fetchone()[0]
        month_msgs = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE created_at >= ?", (month_ago,)
        ).fetchone()[0]
        total_leads = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        week_leads = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE created_at >= ?", (week_ago,)
        ).fetchone()[0]
        top_questions = conn.execute(
            """SELECT text, COUNT(*) as cnt FROM messages
               WHERE created_at >= ? AND length(text) > 10 AND length(text) < 300
               GROUP BY text ORDER BY cnt DESC LIMIT 10""",
            (week_ago,),
        ).fetchall()

    return {
        "total_users": total_users,
        "total_msgs": total_msgs,
        "day_users": day_users,
        "day_msgs": day_msgs,
        "week_users": week_users,
        "week_msgs": week_msgs,
        "month_users": month_users,
        "month_msgs": month_msgs,
        "total_leads": total_leads,
        "week_leads": week_leads,
        "top_questions": top_questions,
    }


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or update.message.chat.type != "private":
        return
    s = get_stats()
    text = (
        f"📊 Статистика бота\n\n"
        f"👥 Всего пользователей: {s['total_users']}\n"
        f"💬 Всего сообщений: {s['total_msgs']}\n\n"
        f"Сегодня: {s['day_users']} польз. / {s['day_msgs']} сообщ.\n"
        f"За 7 дней: {s['week_users']} польз. / {s['week_msgs']} сообщ.\n"
        f"За 30 дней: {s['month_users']} польз. / {s['month_msgs']} сообщ.\n\n"
        f"🔥 Лидов всего: {s['total_leads']} (за неделю +{s['week_leads']})\n"
    )
    if s["top_questions"]:
        text += "\n🔝 Топ-вопросов за неделю:\n"
        for i, (q, cnt) in enumerate(s["top_questions"], 1):
            q_short = q.replace("\n", " ")[:80]
            text += f"{i}. {q_short} — {cnt} раз\n"
    for i in range(0, len(text), 4000):
        await update.message.reply_text(text[i:i + 4000])


# ──────────────────────────────────────────────────────────────────
# Еженедельный дайджест
# ──────────────────────────────────────────────────────────────────

def get_weekly_digest() -> str:
    now = int(time.time())
    week_ago = now - 7 * 86400
    prev_week_ago = now - 14 * 86400

    with _conn() as conn:
        new_users_week = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM messages WHERE created_at >= ?", (week_ago,)
        ).fetchone()[0]
        new_users_prev = conn.execute(
            """SELECT COUNT(DISTINCT user_id) FROM messages
               WHERE created_at >= ? AND created_at < ?""",
            (prev_week_ago, week_ago),
        ).fetchone()[0]
        msgs_week = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE created_at >= ?", (week_ago,)
        ).fetchone()[0]
        leads_week = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE created_at >= ?", (week_ago,)
        ).fetchone()[0]
        leads_prev = conn.execute(
            """SELECT COUNT(*) FROM leads
               WHERE created_at >= ? AND created_at < ?""",
            (prev_week_ago, week_ago),
        ).fetchone()[0]
        by_topic = conn.execute(
            """SELECT topic, COUNT(*) FROM leads
               WHERE created_at >= ? GROUP BY topic ORDER BY COUNT(*) DESC""",
            (week_ago,),
        ).fetchall()
        new_leads_list = conn.execute(
            """SELECT user_id, username, first_name, topic
               FROM leads WHERE created_at >= ? ORDER BY created_at DESC LIMIT 30""",
            (week_ago,),
        ).fetchall()
        top_questions = conn.execute(
            """SELECT text, COUNT(*) as cnt FROM messages
               WHERE created_at >= ? AND length(text) > 10 AND length(text) < 300
               GROUP BY text ORDER BY cnt DESC LIMIT 10""",
            (week_ago,),
        ).fetchall()
        top_users = conn.execute(
            """SELECT username, first_name, COUNT(*) FROM messages
               WHERE created_at >= ?
               GROUP BY user_id ORDER BY COUNT(*) DESC LIMIT 10""",
            (week_ago,),
        ).fetchall()
        first_msgs = conn.execute(
            """SELECT text FROM messages m1
               WHERE created_at >= ?
                 AND created_at = (SELECT MIN(created_at) FROM messages m2
                                   WHERE m2.user_id = m1.user_id)
                 AND length(text) > 10 AND length(text) < 300
               ORDER BY created_at DESC LIMIT 20""",
            (week_ago,),
        ).fetchall()

    topic_names = {
        "registration": "📝 Регистрация",
        "kyc": "🔐 Верификация",
        "deposit": "💳 Пополнение",
        "withdraw": "💸 Вывод",
        "referral": "🤝 Партнёрка",
        "other": "❓ Другое",
    }

    date_str = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    text = f"📅 Дайджест за неделю — {date_str}\n\n"

    text += "👥 ПОЛЬЗОВАТЕЛИ\n"
    text += f"• Активных за неделю: {new_users_week} (неделей ранее: {new_users_prev})\n"
    text += f"• Сообщений: {msgs_week}\n\n"

    text += "🔥 ЛИДЫ\n"
    text += f"• За неделю: {leads_week} (неделей ранее: {leads_prev})\n"
    if by_topic:
        text += "• По темам:\n"
        for topic, cnt in by_topic:
            text += f"   — {topic_names.get(topic, topic)}: {cnt}\n"
    if new_leads_list:
        text += "\n📋 Новые лиды (последние):\n"
        for uid, uname, fname, topic in new_leads_list[:15]:
            nick = f"@{uname}" if uname else (fname or "—")
            text += f"• {nick} (id {uid}) — {topic_names.get(topic, topic)}\n"
        if len(new_leads_list) > 15:
            text += f"… и ещё {len(new_leads_list) - 15}\n"

    text += "\n🔝 ТОП-ВОПРОСОВ\n"
    if top_questions:
        for i, (q, cnt) in enumerate(top_questions, 1):
            q_short = q.replace("\n", " ")[:70]
            text += f"{i}. {q_short} — {cnt} раз\n"
    else:
        text += "Пока нет повторяющихся вопросов.\n"

    text += "\n🗣 О ЧЁМ СПРАШИВАЮТ НОВИЧКИ (первое сообщение)\n"
    if first_msgs:
        for (m,) in first_msgs[:10]:
            m_short = m.replace("\n", " ")[:70]
            text += f"• {m_short}\n"
    else:
        text += "Нет данных.\n"

    text += "\n🏆 САМЫЕ АКТИВНЫЕ\n"
    if top_users:
        for uname, fname, cnt in top_users[:7]:
            nick = f"@{uname}" if uname else (fname or "—")
            text += f"• {nick}: {cnt} сообщ.\n"
    else:
        text += "Нет данных.\n"

    return text
