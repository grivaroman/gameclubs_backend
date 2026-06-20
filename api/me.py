from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models
import schemas
from config import settings
from core.dependencies import get_db, get_current_user_api

router = APIRouter(prefix="/me", tags=["me"])


def _require_user(user: models.User | None) -> models.User:
    if not user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    return user


@router.get("", response_model=schemas.UserMeResponse)
async def get_me(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_api),
):
    user = _require_user(current_user)
    return schemas.UserMeResponse(
        id=user.id,
        email=user.email,
        phone=user.phone,
        balance=user.balance,
        role=user.role,
    )


@router.get("/bookings", response_model=list[schemas.BookingResponse])
async def get_my_bookings(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_api),
):
    user = _require_user(current_user)
    res = await db.execute(
        select(models.Booking)
        .filter(models.Booking.user_id == user.id)
        .order_by(models.Booking.starts_at.desc())
        .limit(50)
    )
    bookings = res.scalars().all()

    pc_ids = list({b.computer_id for b in bookings})
    pcs = {}
    if pc_ids:
        res_pc = await db.execute(select(models.Computer).filter(models.Computer.id.in_(pc_ids)))
        for pc in res_pc.scalars().all():
            pcs[pc.id] = pc

    club_ids = list({pc.club_id for pc in pcs.values()})
    clubs = {}
    if club_ids:
        res_clubs = await db.execute(select(models.Club).filter(models.Club.id.in_(club_ids)))
        for c in res_clubs.scalars().all():
            clubs[c.id] = c

    result = []
    for b in bookings:
        pc = pcs.get(b.computer_id)
        club = clubs.get(pc.club_id) if pc else None
        result.append(schemas.BookingResponse(
            id=b.id,
            computer_id=b.computer_id,
            computer_number=pc.number if pc else None,
            club_id=club.id if club else None,
            club_name=club.name if club else None,
            amount_paid=b.amount_paid,
            status=b.status,
            starts_at=b.starts_at,
            ends_at=b.ends_at,
        ))
    return result


@router.get("/active_booking", response_model=schemas.BookingResponse | None)
async def get_active_booking(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_api),
):
    """Текущее активное бронирование пользователя (если есть)."""
    user = _require_user(current_user)
    res = await db.execute(
        select(models.Booking)
        .filter(models.Booking.user_id == user.id, models.Booking.status == "active")
        .order_by(models.Booking.starts_at.desc())
        .limit(1)
    )
    booking = res.scalars().first()
    if not booking:
        return None

    pc = None
    club = None
    res_pc = await db.execute(select(models.Computer).filter(models.Computer.id == booking.computer_id))
    pc = res_pc.scalars().first()
    if pc:
        res_club = await db.execute(select(models.Club).filter(models.Club.id == pc.club_id))
        club = res_club.scalars().first()

    return schemas.BookingResponse(
        id=booking.id,
        computer_id=booking.computer_id,
        computer_number=pc.number if pc else None,
        club_id=club.id if club else None,
        club_name=club.name if club else None,
        amount_paid=booking.amount_paid,
        status=booking.status,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
    )


@router.get("/transactions", response_model=list[schemas.TransactionResponse])
async def get_my_transactions(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_api),
):
    """История баланса (ledger) пользователя — пополнения и списания."""
    user = _require_user(current_user)
    res = await db.execute(
        select(models.BalanceTransaction)
        .filter(models.BalanceTransaction.user_id == user.id)
        .order_by(models.BalanceTransaction.created_at.desc(), models.BalanceTransaction.id.desc())
        .limit(settings.history_page_size)
    )
    return [
        schemas.TransactionResponse(
            id=t.id, amount=t.amount, balance_after=t.balance_after,
            kind=t.kind, reason=t.reason, created_at=t.created_at,
        )
        for t in res.scalars().all()
    ]


@router.get("/orders", response_model=list[schemas.OrderDetailResponse])
async def get_my_orders(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_api),
):
    user = _require_user(current_user)
    res = await db.execute(
        select(models.Order)
        .filter(models.Order.user_id == user.id)
        .order_by(models.Order.created_at.desc())
        .limit(50)
    )
    orders = res.scalars().all()

    product_ids = list({o.product_id for o in orders if o.product_id})
    products = {}
    if product_ids:
        res_prod = await db.execute(select(models.Product).filter(models.Product.id.in_(product_ids)))
        for p in res_prod.scalars().all():
            products[p.id] = p

    club_ids = list({p.club_id for p in products.values()})
    clubs = {}
    if club_ids:
        res_clubs = await db.execute(select(models.Club).filter(models.Club.id.in_(club_ids)))
        for c in res_clubs.scalars().all():
            clubs[c.id] = c

    result = []
    for o in orders:
        product = products.get(o.product_id) if o.product_id else None
        club = clubs.get(product.club_id) if product else None
        result.append(schemas.OrderDetailResponse(
            id=o.id,
            product_id=o.product_id,
            product_name=product.name if product else None,
            club_id=club.id if club else None,
            club_name=club.name if club else None,
            amount_paid=o.amount_paid,
            status=o.status,
            created_at=o.created_at,
        ))
    return result
