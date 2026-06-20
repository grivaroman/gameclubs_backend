"""Токены мобильного API: короткий access-JWT + отзываемый refresh-токен.

Access — обычный JWT (его проверяет core.dependencies.get_current_user_api),
но с коротким TTL (settings.mobile_access_token_expire_minutes).
Refresh — непрозрачный токен; в БД хранится только sha256 (models.RefreshToken).
Ротация при каждом /api/refresh, reuse-detection при предъявлении отозванного.

Время — naive UTC (datetime.utcnow), как во всей кодовой базе.
"""
import hashlib
import secrets
from datetime import datetime, timedelta

from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models
from config import settings
from core.observability import get_logger
from core.roles import is_valid_role

logger = get_logger("api_tokens")

REFRESH_TOKEN_BYTES = 32


def create_mobile_access_token(email: str) -> str:
    now = datetime.utcnow()
    payload = {
        "sub": email,
        "iat": int(now.timestamp()),
        "exp": now + timedelta(minutes=settings.mobile_access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def access_token_expires_in_seconds() -> int:
    return settings.mobile_access_token_expire_minutes * 60


def _generate_refresh_token() -> str:
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def _hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def issue_refresh_token(
    db: AsyncSession, user: models.User, *, user_agent: str | None = None, ip: str | None = None
) -> str:
    """Создаёт запись refresh-токена, возвращает СЫРОЙ токен (показывается один раз)."""
    raw = _generate_refresh_token()
    now = datetime.utcnow()
    db.add(models.RefreshToken(
        user_id=user.id,
        token_hash=_hash_refresh_token(raw),
        issued_at=now,
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        user_agent=(user_agent or "")[:255] or None,
        created_ip=ip,
    ))
    return raw


async def _get_row(db: AsyncSession, raw: str) -> models.RefreshToken | None:
    res = await db.execute(
        select(models.RefreshToken).filter(models.RefreshToken.token_hash == _hash_refresh_token(raw))
    )
    return res.scalars().first()


async def revoke_all_user_refresh_tokens(db: AsyncSession, user_id: int) -> None:
    now = datetime.utcnow()
    res = await db.execute(
        select(models.RefreshToken).filter(
            models.RefreshToken.user_id == user_id,
            models.RefreshToken.revoked_at.is_(None),
        )
    )
    for row in res.scalars().all():
        row.revoked_at = now


async def rotate_refresh_token(
    db: AsyncSession, raw: str, *, user_agent: str | None = None, ip: str | None = None
) -> tuple[models.User, str] | None:
    """Проверяет refresh, отзывает старый, выдаёт новый. None если невалиден.

    Предъявление уже отозванного токена = компрометация → отзыв всей семьи юзера.
    """
    row = await _get_row(db, raw)
    if row is None:
        return None

    now = datetime.utcnow()

    if row.revoked_at is not None:
        await revoke_all_user_refresh_tokens(db, row.user_id)
        await db.commit()
        logger.warning("refresh_token_reuse", extra={"user_id": row.user_id})
        return None

    if row.expires_at <= now:
        return None

    res = await db.execute(select(models.User).filter(models.User.id == row.user_id))
    user = res.scalars().first()
    if not user or not user.is_active or not is_valid_role(user.role):
        return None
    # Смена пароля/logout-all инвалидирует refresh, выданные до cutoff.
    if user.tokens_invalid_before is not None and row.issued_at < user.tokens_invalid_before:
        return None

    row.revoked_at = now
    row.last_used_at = now
    new_raw = await issue_refresh_token(db, user, user_agent=user_agent, ip=ip)
    return user, new_raw


async def revoke_refresh_token(db: AsyncSession, raw: str) -> bool:
    """Отзывает один refresh-токен (logout). True если был активен."""
    row = await _get_row(db, raw)
    if row is None or row.revoked_at is not None:
        return False
    row.revoked_at = datetime.utcnow()
    return True
