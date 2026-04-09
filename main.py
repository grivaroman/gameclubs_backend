from web import router as web_router
from api import router as api_router
from core.ws import manager

import asyncio
from datetime import datetime
from sqlalchemy.future import select
from fastapi import WebSocket, WebSocketDisconnect

app = FastAPI(title="CyberBooking System")

async def cleanup_expired_sessions():
    """Фоновая задача: освобождает ПК, если время брони вышло"""
    while True:
        await asyncio.sleep(60) # Проверка раз в минуту
        async with models.SessionLocal() as db:
            now = datetime.utcnow()
            res = await db.execute(
                select(models.Computer).filter(
                    models.Computer.status == "busy",
                    models.Computer.end_time <= now
                )
            )
            expired_pcs = res.scalars().all()
            for pc in expired_pcs:
                pc.status = "free"
                pc.current_user_id = None
                pc.end_time = None
                # Отправляем команду блокировки по WebSocket
                await manager.send_command(pc.id, {"command": "lock"})
            
            if expired_pcs:
                await db.commit()
                print(f">>> CLEANUP: Освобождено ПК: {len(expired_pcs)}")

@app.on_event("startup")
async def startup():
    async with models.engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    asyncio.create_task(cleanup_expired_sessions())

@app.websocket("/ws/pc/{pc_id}")
async def websocket_pc_endpoint(websocket: WebSocket, pc_id: int):
    """Эндпоинт для подключения клиентской части ПК (Шелл)"""
    await manager.connect(pc_id, websocket)
    try:
        while True:
            await websocket.receive_text() # Просто держим соединение
    except WebSocketDisconnect:
        manager.disconnect(pc_id)

@app.get("/", response_class=HTMLResponse)
async def index():
    return RedirectResponse(url="/login")

app.include_router(web_router)
app.include_router(api_router)