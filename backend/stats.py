"""
stats.py — простая статистика бота на SQLite.
Хранит сообщения пользователей и умеет показывать сводку по команде /stats.
"""
import sqlite3
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

DB_PATH = "stats.db"


def init_db():
    """Создаёт таблицу для хранения сообщений, если её ещё нет."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            text TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def log_message(user_id: int, username: str | None, text: str | None):
    """Сохраняет одно сообщение пользователя в базу."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO messages (user_id, username, text, created_at) VALUES (?, ?, ?, ?)",
        (user_id, username, text, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def get_stats():
    """Возвращает базовую сводку: сколько всего сообщений и сколько уникальных пользователей."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM messages")
    total_messages = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT user_id) FROM messages")
    unique_users = cur.fetchone()[0]

    conn.close()
    return {
        "total_messages": total_messages,
        "unique_users": unique_users,
    }


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /stats — присылает сводку прямо в чат."""
    data = get_stats()
    await update.message.reply_text(
        f"📊 Статистика бота:\n"
        f"Сообщений всего: {data['total_messages']}\n"
        f"Уникальных пользователей: {data['unique_users']}"
    )
