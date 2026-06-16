import hashlib
import hmac
import secrets
from datetime import datetime
from typing import Dict

from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models

PC_TOKEN_BYTES = 32
PC_TOKEN_PREFIX = "pc_"


class ConnectionManager:
    def __init__(self):
        # Храним активные соединения: {pc_id: websocket}
        self.active_connections: Dict[int, WebSocket] = {}

    async def connect(self, pc_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[pc_id] = websocket

    def disconnect(self, pc_id: int):
        if pc_id in self.active_connections:
            del self.active_connections[pc_id]

    async def send_command(self, pc_id: int, message: dict):
        if pc_id in self.active_connections:
            await self.active_connections[pc_id].send_json(message)


def generate_pc_token() -> str:
    return f"{PC_TOKEN_PREFIX}{secrets.token_urlsafe(PC_TOKEN_BYTES)}"


def hash_pc_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_pc_token(token: str | None, token_hash: str | None) -> bool:
    if not token or not token_hash:
        return False
    return hmac.compare_digest(hash_pc_token(token), token_hash)


async def issue_pc_token(db: AsyncSession, pc: models.Computer) -> str:
    token = generate_pc_token()
    pc.ws_token_hash = hash_pc_token(token)
    pc.ws_token_created_at = datetime.utcnow()
    await db.flush()
    return token


async def authenticate_pc_websocket(db: AsyncSession, pc_id: int, token: str | None) -> models.Computer | None:
    res = await db.execute(select(models.Computer).filter(models.Computer.id == pc_id))
    pc = res.scalars().first()
    if not pc or not verify_pc_token(token, pc.ws_token_hash):
        return None
    return pc


manager = ConnectionManager()


async def safe_send_pc_command(pc_id: int, message: dict) -> None:
    """Отправка команды ПК без падения вызывающего кода при ошибке сокета."""
    try:
        await manager.send_command(pc_id, message)
    except Exception:
        pass


class UserConnectionManager:
    """WebSocket соединения для пользователей мобильного приложения."""

    def __init__(self):
        self.connections: dict[int, WebSocket] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.connections[user_id] = websocket

    def disconnect(self, user_id: int):
        self.connections.pop(user_id, None)

    async def send_event(self, user_id: int, event: dict):
        ws = self.connections.get(user_id)
        if ws:
            try:
                await ws.send_json(event)
            except Exception:
                self.disconnect(user_id)


user_manager = UserConnectionManager()
