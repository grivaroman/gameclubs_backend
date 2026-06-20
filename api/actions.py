"""
JSON API actions для мобильного приложения.

Тонкий транспортный слой: валидирует вход, вызывает сервис и переводит
доменные исключения (ServiceError) в HTTPException. Бизнес-логика — в
core/services/*.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

import models
import schemas
from config import settings
from core.dependencies import get_db, get_current_user_api
from core.ratelimit import PAYMENT_LIMIT, enforce_rate_limit
from core.services.booking_service import BookingService
from core.services.exceptions import ServiceError
from core.services.order_service import OrderService
from core.services.payment_service import PaymentService
from core.services.review_service import ReviewService

router = APIRouter(tags=["actions"])


class BookSeatRequest(BaseModel):
    package_id: int


class BookRequestBody(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class KaspiTestRequest(BaseModel):
    amount: int


def _require_user(user: models.User | None) -> models.User:
    if not user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    return user


def _as_http(error: ServiceError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.message)


@router.post("/book_seat/{pc_id}", response_model=schemas.ActionResponse)
async def api_book_seat(
    pc_id: int,
    body: BookSeatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_api),
):
    user = _require_user(current_user)
    try:
        result = await BookingService(db).book_seat(
            user_id=user.id, pc_id=pc_id, package_id=body.package_id
        )
    except ServiceError as error:
        raise _as_http(error)
    return schemas.ActionResponse(status="success", message=result.message)


@router.post("/book_request/{pc_id}", response_model=schemas.ActionResponse)
async def api_book_request(
    pc_id: int,
    body: BookRequestBody | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_api),
):
    """Заявка на бронь места (агрегатор). Режим (бесплатно/депозит) задаёт клуб."""
    user = _require_user(current_user)
    body = body or BookRequestBody()
    try:
        result = await BookingService(db).create_booking_request(
            user_id=user.id, pc_id=pc_id, starts_at=body.starts_at, ends_at=body.ends_at
        )
    except ServiceError as error:
        raise _as_http(error)
    return schemas.ActionResponse(status="success", message=result.message)


@router.post("/bookings/{booking_id}/cancel", response_model=schemas.ActionResponse)
async def api_cancel_booking_request(
    booking_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_api),
):
    """Игрок отменяет свою pending-заявку (депозит возвращается)."""
    user = _require_user(current_user)
    try:
        result = await BookingService(db).cancel_request(user_id=user.id, booking_id=booking_id)
    except ServiceError as error:
        raise _as_http(error)
    return schemas.ActionResponse(status="success", message=result.message)


@router.post("/free_seat/{pc_id}", response_model=schemas.ActionResponse)
async def api_free_seat(
    pc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_api),
):
    user = _require_user(current_user)
    try:
        result = await BookingService(db).free_seat(actor=user, pc_id=pc_id)
    except ServiceError as error:
        raise _as_http(error)
    return schemas.ActionResponse(status="success", message=result.message)


@router.post("/buy_product/{product_id}", response_model=schemas.ActionResponse)
async def api_buy_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_api),
):
    user = _require_user(current_user)
    try:
        result = await OrderService(db).buy_product(user_id=user.id, product_id=product_id)
    except ServiceError as error:
        raise _as_http(error)
    return schemas.ActionResponse(status="success", message=result.message)


@router.post("/payments/kaspi/test")
async def api_kaspi_test_payment(
    body: KaspiTestRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_api),
):
    # Доступность эндпоинта — транспортная проверка, выполняется до авторизации.
    if not settings.enable_kaspi_test_payment:
        raise HTTPException(status_code=404, detail="Эндпоинт недоступен")
    user = _require_user(current_user)
    limited = await enforce_rate_limit(request, "kaspi_test", PAYMENT_LIMIT)
    if limited:
        return limited
    try:
        result = await PaymentService(db).kaspi_test_top_up(user_id=user.id, amount=body.amount)
    except ServiceError as error:
        raise _as_http(error)
    return {
        "status": "success",
        "message": result.message,
        "balance": result.balance,
        "reference": result.reference,
    }


@router.post("/clubs/{club_id}/review", response_model=schemas.ActionResponse)
async def api_submit_review(
    club_id: int,
    body: schemas.ReviewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User | None = Depends(get_current_user_api),
):
    user = _require_user(current_user)
    try:
        result = await ReviewService(db).submit_review(
            user_id=user.id, club_id=club_id, rating=body.rating, comment=body.comment
        )
    except ServiceError as error:
        raise _as_http(error)
    return schemas.ActionResponse(status="success", message=result.message)
