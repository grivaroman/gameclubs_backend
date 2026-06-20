"""Проверки доступа сервисного слоя.

Делегируют в core.tenancy — единый источник правды по правам, чтобы логика
«может ли пользователь управлять клубом» не дублировалась между web и services.
"""
from sqlalchemy.ext.asyncio import AsyncSession

import models
from core.tenancy import can_manage_club


async def user_can_manage_club(db: AsyncSession, user: models.User, club_id: int) -> bool:
    return await can_manage_club(db, user, club_id)
