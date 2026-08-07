"""
database.py — работа с SQLite базой данных для Binibit Team Mini App.
"""

import sqlite3
from datetime import datetime

DB_PATH = "binibit_tma.db"
DEFAULT_BINIBIT_REF = "https://binibit.com/?i=5kjbt1"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Создаёт таблицу users, если её ещё нет."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            invited_by INTEGER,
            binibit_ref_link TEXT DEFAULT '{DEFAULT_BINIBIT_REF}',
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def get_user(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def create_user_if_not_exists(user_id: int, username: str, invited_by: int | None):
    """Создаёт пользователя, если его ещё нет в базе. Фиксирует, кто его пригласил."""
    existing = get_user(user_id)
    if existing:
        return existing

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO users (user_id, username, invited_by, binibit_ref_link, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, username, invited_by, DEFAULT_BINIBIT_REF, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    return get_user(user_id)


def update_ref_link(user_id: int, ref_link: str):
    """Сохраняет личную реферальную ссылку пользователя в Binibit."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET binibit_ref_link = ? WHERE user_id = ?",
        (ref_link, user_id)
    )
    conn.commit()
    conn.close()
    return get_user(user_id)


def get_effective_ref_link(user_id: int) -> str:
    """
    Возвращает реф-ссылку, по которой должен регистрироваться новичок,
    приглашённый пользователем user_id (то есть его пригласителем).
    Если у пригласителя нет своей ссылки — возвращает дефолтную.
    """
    user = get_user(user_id)
    if user and user.get("binibit_ref_link"):
        return user["binibit_ref_link"]
    return DEFAULT_BINIBIT_REF


def get_first_line_count(user_id: int) -> int:
    """Количество лично приглашённых пользователей (1-я линия)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM users WHERE invited_by = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row["cnt"] if row else 0


def get_team_count(user_id: int) -> int:
    """
    Общий размер команды (все уровни вниз по дереву рефералов) —
    обход в ширину по invited_by.
    """
    conn = get_connection()
    cur = conn.cursor()

    total = 0
    current_level = [user_id]

    while current_level:
        placeholders = ",".join("?" for _ in current_level)
        cur.execute(
            f"SELECT user_id FROM users WHERE invited_by IN ({placeholders})",
            current_level
        )
        next_level = [row["user_id"] for row in cur.fetchall()]
        total += len(next_level)
        current_level = next_level

    conn.close()
    return total
