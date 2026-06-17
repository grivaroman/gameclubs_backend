from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models
import schemas
from core.dependencies import get_db, get_current_user_api
from core.roles import CLUB_ADMIN_ROLES, ROLE_SUPERADMIN
from core.services.access import user_can_manage_club

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[schemas.NotificationResponse])
async def get_notifications(
    request: Request,
    unread_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_api),
):
    """
    Уведомления клуба для администраторов/владельцев.
    Обычные пользователи получают пустой список (уведомления для них
    приходят через WebSocket /ws/user).
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")

    if current_user.role not in CLUB_ADMIN_ROLES and current_user.role != ROLE_SUPERADMIN:
        return []

    stmt = select(models.Notification).order_by(models.Notification.created_at.desc()).limit(100)

    if current_user.role != ROLE_SUPERADMIN:
        res_clubs = await db.execute(
            select(models.Club.id).filter(
                models.Club.owner_id == current_user.id,
                models.Club.status == "active",
            )
        )
        club_ids = [row[0] for row in res_clubs.all()]
        if not club_ids:
            return []
        stmt = stmt.filter(models.Notification.club_id.in_(club_ids))

    if unread_only:
        stmt = stmt.filter(models.Notification.is_read == 0)

    res = await db.execute(stmt)
    notifications = res.scalars().all()
    return [
        schemas.NotificationResponse(
            id=n.id,
            kind=n.kind,
            title=n.title,
            message=n.message,
            is_read=bool(n.is_read),
            created_at=n.created_at,
        )
        for n in notifications
    ]


@router.post("/{notification_id}/read", response_model=schemas.ActionResponse)
async def mark_notification_read(
    notification_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_api),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")

    # Уведомления — для персонала клуба. Обычный игрок их даже не видит в списке,
    # поэтому помечать прочитанным он ничего не должен.
    if current_user.role not in CLUB_ADMIN_ROLES and current_user.role != ROLE_SUPERADMIN:
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    res = await db.execute(
        select(models.Notification).filter(models.Notification.id == notification_id)
    )
    notification = res.scalars().first()
    if not notification:
        raise HTTPException(status_code=404, detail="Уведомление не найдено")

    # Tenancy: владелец может трогать только уведомления своих клубов (IDOR → 403).
    if current_user.role != ROLE_SUPERADMIN:
        if notification.club_id is None or not await user_can_manage_club(
            db, current_user, notification.club_id
        ):
            raise HTTPException(status_code=403, detail="Нет доступа к этому уведомлению")

    notification.is_read = 1
    await db.commit()
    return schemas.ActionResponse(status="success", message="Отмечено как прочитанное")
