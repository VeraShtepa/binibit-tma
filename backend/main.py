"""
main.py — FastAPI backend для Binibit Team Mini App.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

import database as db

app = FastAPI(title="Binibit TMA API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()

# Ссылки-константы
OFFICIAL_CHANNEL_URL = "https://t.me/binibitnews"
INSTRUCTIONS_CHAT_URL = "https://t.me/binibit_bini"
TEAM_COMMUNITY_CHAT_URL = "https://t.me/+4TNM-P6FdQY4YWI0"

# Имя бота — используется для сборки реферальной ссылки на само мини-приложение.
# Поменяй на юзернейм своего бота (без @).
BOT_USERNAME = "Assistentvdele_Bot"


class RegisterPayload(BaseModel):
    user_id: int
    username: str | None = None
    invited_by: int | None = None


class RefLinkPayload(BaseModel):
    user_id: int
    ref_link: str


@app.post("/api/register")
def register_user(payload: RegisterPayload):
    """
    Вызывается при открытии приложения. Создаёт пользователя, если его ещё нет,
    и фиксирует, кто его пригласил (invited_by берётся из startapp-параметра).
    """
    user = db.create_user_if_not_exists(
        user_id=payload.user_id,
        username=payload.username,
        invited_by=payload.invited_by,
    )

    # Ссылка, по которой этому пользователю нужно регистрироваться в Binibit —
    # это личная ссылка ЕГО пригласителя (или дефолтная, если пригласителя нет/без ссылки)
    if user["invited_by"]:
        signup_ref_link = db.get_effective_ref_link(user["invited_by"])
    else:
        signup_ref_link = db.DEFAULT_BINIBIT_REF

    return {
        "user": user,
        "signup_ref_link": signup_ref_link,
        "official_channel_url": OFFICIAL_CHANNEL_URL,
        "instructions_chat_url": INSTRUCTIONS_CHAT_URL,
        "team_community_chat_url": TEAM_COMMUNITY_CHAT_URL,
        "invite_link": f"https://t.me/{BOT_USERNAME}/app?startapp={payload.user_id}",
    }


@app.post("/api/ref-link")
def set_ref_link(payload: RefLinkPayload):
    """Сохраняет личную реферальную ссылку пользователя в Binibit (вкладка «Кабинет»)."""
    user = db.update_ref_link(payload.user_id, payload.ref_link)
    return {"user": user}


@app.get("/api/stats/{user_id}")
def get_stats(user_id: int):
    """Статистика команды: 1-я линия + вся структура (вкладка «Команда»)."""
    return {
        "first_line": db.get_first_line_count(user_id),
        "team_total": db.get_team_count(user_id),
    }


# --- Раздача frontend ---
@app.get("/")
def serve_index():
    return FileResponse("index.html")
