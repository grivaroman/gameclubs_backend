import asyncio
from datetime import datetime

from api import router as api_router
from core.ws import manager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.future import select
from web import router as web_router

import models

app = FastAPI(title="CyberBooking System")


async def ensure_extra_columns():
    additions = {
        "clubs": {
            "city": "VARCHAR DEFAULT ''",
            "photo_url": "VARCHAR",
            "contact_phone": "VARCHAR",
            "working_hours": "VARCHAR DEFAULT '24/7'",
            "owner_id": "INTEGER",
        },
        "notifications": {
            "club_id": "INTEGER",
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
                db.add(models.Notification(
                    kind="expired",
                    club_id=pc.club_id,
                    title="Время истекло",
                    message=f"ПК #{pc.number}: время сессии завершилось.",
                ))
                await manager.send_command(pc.id, {"command": "lock"})

            if expired_pcs:
                await db.commit()
                print(f">>> CLEANUP: Освобождено ПК: {len(expired_pcs)}")


@app.on_event("startup")
async def startup():
    async with models.engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    await ensure_extra_columns()
    await populate_base_games()
    asyncio.create_task(cleanup_expired_sessions())


@app.websocket("/ws/pc/{pc_id}")
async def websocket_pc_endpoint(websocket: WebSocket, pc_id: int):
    """Эндпоинт для подключения клиентской части ПК."""
    await manager.connect(pc_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(pc_id)


@app.get("/", response_class=HTMLResponse)
async def index():
    return RedirectResponse(url="/login")


app.include_router(web_router)
app.include_router(api_router)
