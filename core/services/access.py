"""Общие проверки доступа, используемые web- и api-слоями."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models
from core.roles import CLUB_ADMIN_ROLES, ROLE_SUPERADMIN


async def user_can_manage_club(db: AsyncSession, user: models.User, club_id: int) -> bool:
    """True, если пользователь — суперадмин или владелец активного клуба."""
    if user.role == ROLE_SUPERADMIN:
        return True
    if user.role not in CLUB_ADMIN_ROLES:
        return False
    res = await db.execute(
        select(models.Club.id).filter(
            models.Club.id == club_id,
            models.Club.owner_id == user.id,
            models.Club.status == "active",
        )
    )
    return res.scalars().first() is not None
