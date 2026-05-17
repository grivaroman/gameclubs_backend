from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

import models
from core.dependencies import get_current_user, get_db, templates
from core.roles import ROLE_ADMIN, ROLE_PENDING_OWNER, ROLE_SUPERADMIN, ROLE_USER

router = APIRouter(tags=["web_superadmin"])


async def require_superadmin(request: Request, db: AsyncSession):
    current_user = await get_current_user(request, db)
    if not current_user or current_user.role != ROLE_SUPERADMIN:
        return None
    return current_user


@router.get("/superadmin", response_class=HTMLResponse)
async def superadmin_page(request: Request, db: AsyncSession = Depends(get_db)):
    current_user = await require_superadmin(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    res_pending = await db.execute(
        select(models.Club)
        .options(selectinload(models.Club.owner), selectinload(models.Club.games))
        .filter(models.Club.status == "pending")
        .order_by(models.Club.submitted_at.desc())
    )
    pending_clubs = res_pending.scalars().all()

    res_clubs = await db.execute(
        select(models.Club)
        .options(selectinload(models.Club.owner))
        .order_by(models.Club.status, models.Club.name)
    )
    clubs = res_clubs.scalars().all()

    res_users = await db.execute(select(models.User).order_by(models.User.role, models.User.email))
    users = res_users.scalars().all()

    stats = {
        "pending": len([club for club in clubs if club.status == "pending"]),
        "active": len([club for club in clubs if club.status == "active"]),
        "blocked": len([club for club in clubs if club.status == "blocked"]),
        "users": len(users),
    }
    return templates.TemplateResponse("superadmin.html", {
        "request": request,
        "current_user": current_user,
        "pending_clubs": pending_clubs,
        "clubs": clubs,
        "users": users,
        "stats": stats,
    })


@router.post("/superadmin/clubs/{club_id}/approve")
async def approve_club(club_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    current_user = await require_superadmin(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    res = await db.execute(select(models.Club).options(selectinload(models.Club.owner)).filter(models.Club.id == club_id))
    club = res.scalars().first()
    if club:
        club.status = "active"
        club.approved_at = datetime.utcnow()
        club.moderation_comment = None
        if club.owner:
            club.owner.role = ROLE_ADMIN
            club.owner.is_active = 1
        db.add(models.Notification(
            kind="moderation",
            club_id=club.id,
            title="Клуб одобрен",
            message=f"{club.name} опубликован и доступен клиентам.",
        ))
        await db.commit()
    return RedirectResponse(url="/superadmin", status_code=303)


@router.post("/superadmin/clubs/{club_id}/reject")
async def reject_club(
    club_id: int,
    request: Request,
    comment: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    current_user = await require_superadmin(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    res = await db.execute(select(models.Club).options(selectinload(models.Club.owner)).filter(models.Club.id == club_id))
    club = res.scalars().first()
    if club:
        club.status = "rejected"
        club.moderation_comment = comment or "Заявка отклонена. Свяжитесь с поддержкой."
        if club.owner and club.owner.role == ROLE_PENDING_OWNER:
            club.owner.role = ROLE_USER
        await db.commit()
    return RedirectResponse(url="/superadmin", status_code=303)


@router.post("/superadmin/clubs/{club_id}/block")
async def block_club(
    club_id: int,
    request: Request,
    comment: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    current_user = await require_superadmin(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    res = await db.execute(select(models.Club).filter(models.Club.id == club_id))
    club = res.scalars().first()
    if club:
        club.status = "blocked"
        club.moderation_comment = comment or "Клуб временно заблокирован."
        await db.commit()
    return RedirectResponse(url="/superadmin", status_code=303)


@router.post("/superadmin/clubs/{club_id}/restore")
async def restore_club(club_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    current_user = await require_superadmin(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    res = await db.execute(select(models.Club).options(selectinload(models.Club.owner)).filter(models.Club.id == club_id))
    club = res.scalars().first()
    if club:
        club.status = "active"
        club.moderation_comment = None
        if club.owner and club.owner.role in (ROLE_PENDING_OWNER, ROLE_USER):
            club.owner.role = ROLE_ADMIN
        await db.commit()
    return RedirectResponse(url="/superadmin", status_code=303)
