import asyncio
from datetime import datetime

from api import router as api_router
from config import settings
from core.roles import ROLE_SUPERADMIN
from core.security import CSRFMiddleware, SecurityHeadersMiddleware, split_csv
from core.ws import authenticate_pc_websocket, manager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from passlib.context import CryptContext
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text, update
from sqlalchemy.future import select
from starlette.middleware.trustedhost import TrustedHostMiddleware
from web import router as web_router

import models

app = FastAPI(title="CyberBooking System")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=split_csv(settings.allowed_hosts) or ["*"])


async def ensure_extra_columns():
    additions = {
        "clubs": {
            "city": "VARCHAR DEFAULT ''",
            "photo_url": "VARCHAR",
            "contact_phone": "VARCHAR",
            "working_hours": "VARCHAR DEFAULT '24/7'",
            "owner_id": "INTEGER",
            "status": "VARCHAR DEFAULT 'active'",
            "moderation_comment": "TEXT",
            "submitted_at": "TIMESTAMP",
            "approved_at": "TIMESTAMP",
        },
        "users": {
            "is_active": "INTEGER DEFAULT 1",
        },
        "notifications": {
            "club_id": "INTEGER",
        },
        "computers": {
            "ws_token_hash": "VARCHAR",
            "ws_token_created_at": "TIMESTAMP",
        },
    }
    async with models.engine.begin() as conn:
        for table, columns in additions.items():
            for column, definition in columns.items():
                try:
                    await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition}"))
                except Exception:
                    pass


async def populate_base_games():
    base_games = [
        "Dota 2",
        "CS2",
        "Valorant",
        "League of Legends",
        "Warzone",
        "Apex Legends",
        "Minecraft",
        "GTA V",
        "Mortal Kombat 1",
        "FC 25",
    ]
    async with models.SessionLocal() as db:
        for game_name in base_games:
            res = await db.execute(select(models.Game).filter(models.Game.name == game_name))
            if not res.scalars().first():
                db.add(models.Game(name=game_name))
        await db.commit()


async def bootstrap_superadmin():
    if not settings.superadmin_email or not settings.superadmin_password:
        return
    async with models.SessionLocal() as db:
        email = settings.superadmin_email.strip().lower()
        res = await db.execute(select(models.User).filter(models.User.email == email))
        user = res.scalars().first()
        if user:
            if user.role != ROLE_SUPERADMIN:
                user.role = ROLE_SUPERADMIN
                await db.commit()
            return

        db.add(models.User(
            email=email,
            hashed_password=pwd_context.hash(settings.superadmin_password),
            role=ROLE_SUPERADMIN,
            is_active=1,
        ))
        await db.commit()


async def cleanup_expired_sessions():
    """Фоновая задача: освобождает ПК, если время брони вышло."""
    while True:
        await asyncio.sleep(60)
        async with models.SessionLocal() as db:
            now = datetime.utcnow()
            res = await db.execute(
                select(models.Computer).filter(
                    models.Computer.status == "busy",
                    models.Computer.end_time <= now,
                )
            )
            expired_pcs = res.scalars().all()
            for pc in expired_pcs:
                pc.status = "free"
                pc.current_user_id = None
                pc.end_time = None
                await db.execute(
                    update(models.Booking)
                    .filter(models.Booking.computer_id == pc.id, models.Booking.status == "active")
                    .values(status="expired")
                )
                db.add(models.Notification(
                    kind="expired",
                    club_id=pc.club_id,
                    title="Время истекло",
                    message=f"ПК #{pc.number}: время сессии завершилось.",
                ))
                try:
                    await manager.send_command(pc.id, {"command": "lock"})
                except Exception:
                    pass

            if expired_pcs:
                await db.commit()
                print(f">>> CLEANUP: Освобождено ПК: {len(expired_pcs)}")


@app.on_event("startup")
async def startup():
    if settings.auto_create_db_schema:
        async with models.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        await ensure_extra_columns()
    await populate_base_games()
    await bootstrap_superadmin()
    asyncio.create_task(cleanup_expired_sessions())


@app.websocket("/ws/pc/{pc_id}")
async def websocket_pc_endpoint(websocket: WebSocket, pc_id: int):
    """Эндпоинт для подключения клиентской части ПК."""
    token = websocket.query_params.get("token") or websocket.headers.get("x-pc-token")
    async with models.SessionLocal() as db:
        pc = await authenticate_pc_websocket(db, pc_id, token)
    if not pc:
        await websocket.close(code=1008)
        return

    await manager.connect(pc_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(pc_id)


@app.get("/", response_class=HTMLResponse)
async def index():
    return RedirectResponse(url="/login")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    async with models.engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ready"}


app.include_router(web_router)
app.include_router(api_router)
