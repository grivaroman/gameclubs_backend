from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models
from core.roles import CLUB_ADMIN_ROLES, ROLE_SUPERADMIN


async def manageable_club_ids(db: AsyncSession, user: models.User) -> list[int]:
    if user.role == ROLE_SUPERADMIN:
        res = await db.execute(select(models.Club.id).filter(models.Club.status == "active"))
    elif user.role in CLUB_ADMIN_ROLES:
        res = await db.execute(
            select(models.Club.id).filter(
                models.Club.owner_id == user.id,
                models.Club.status == "active",
            )
        )
    else:
        return []
    return list(res.scalars().all())


async def can_manage_club(db: AsyncSession, user: models.User, club_id: int | None) -> bool:
    if not club_id:
        return False
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


async def can_manage_pc(db: AsyncSession, user: models.User, pc: models.Computer | None) -> bool:
    return bool(pc and await can_manage_club(db, user, pc.club_id))


async def can_manage_product(db: AsyncSession, user: models.User, product: models.Product | None) -> bool:
    return bool(product and await can_manage_club(db, user, product.club_id))


async def can_manage_order(db: AsyncSession, user: models.User, order: models.Order | None) -> bool:
    if not order or not order.product:
        return False
    return await can_manage_product(db, user, order.product)
