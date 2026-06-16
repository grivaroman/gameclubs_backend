from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

import models
from config import settings
from core.dependencies import templates, get_db, get_current_user
from core.ratelimit import PAYMENT_LIMIT, enforce_rate_limit
from core.services.booking_service import BookingService
from core.services.exceptions import ServiceError
from core.services.order_service import OrderService
from core.services.payment_service import PaymentService
from core.services.review_service import ReviewService

router = APIRouter(tags=["web_user"])


async def club_card_stats(db: AsyncSession, club_ids: list[int]):
    stats = {}
    for club_id in club_ids:
        res = await db.execute(select(models.Computer).filter(models.Computer.club_id == club_id))
        computers = res.scalars().all()
        res_products = await db.execute(
            select(models.Product).filter(models.Product.club_id == club_id)
        )
        products = res_products.scalars().all()
        res_reviews = await db.execute(
            select(
                func.count(models.ClubReview.id),
                func.coalesce(func.avg(models.ClubReview.rating), 0),
            ).filter(models.ClubReview.club_id == club_id)
        )
        review_count, rating_avg = res_reviews.one()
        stats[club_id] = {
            "total": len(computers),
            "free": len([pc for pc in computers if pc.status == "free"]),
            "busy": len([pc for pc in computers if pc.status == "busy"]),
            "reserved": len([pc for pc in computers if pc.status == "reserved"]),
            "products": len(products),
            "review_count": review_count or 0,
            "rating_avg": round(float(rating_avg or 0), 1),
        }
    return stats


@router.post("/book_seat/{pc_id}")
async def book_seat(
    request: Request,
    pc_id: int,
    package_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    current_user = await get_current_user(request, db)
    if not current_user or not current_user.is_active:
        return {"status": "error", "message": "Необходима авторизация"}
    try:
        result = await BookingService(db).book_seat(
            user_id=current_user.id, pc_id=pc_id, package_id=package_id
        )
    except ServiceError as error:
        return {"status": "error", "message": error.message}
    return {"status": "success", "message": result.message}


@router.post("/free_seat/{pc_id}")
async def free_seat(request: Request, pc_id: int, db: AsyncSession = Depends(get_db)):
    current_user = await get_current_user(request, db)
    if not current_user or not current_user.is_active:
        return {"status": "error", "message": "Необходима авторизация"}
    try:
        result = await BookingService(db).free_seat(actor=current_user, pc_id=pc_id)
    except ServiceError as error:
        return {"status": "error", "message": error.message}
    return {"status": "success", "message": result.message}


@router.post("/buy_product/{product_id}")
async def buy_product(request: Request, product_id: int, db: AsyncSession = Depends(get_db)):
    current_user = await get_current_user(request, db)
    if not current_user or not current_user.is_active:
        return {"status": "error", "message": "Сначала зарегистрируйтесь или войдите"}
    try:
        result = await OrderService(db).buy_product(user_id=current_user.id, product_id=product_id)
    except ServiceError as error:
        return {"status": "error", "message": error.message}
    return {"status": "success", "message": result.message}


@router.post("/payments/kaspi/test")
async def kaspi_test_payment(
    request: Request,
    amount: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # Доступность эндпоинта — транспортная проверка, выполняется до авторизации.
    if not settings.enable_kaspi_test_payment:
        return JSONResponse({"status": "error", "message": "Эндпоинт недоступен"}, status_code=404)
    limited = await enforce_rate_limit(request, "kaspi_test", PAYMENT_LIMIT)
    if limited:
        return limited
    current_user = await get_current_user(request, db)
    if not current_user or not current_user.is_active:
        return {"status": "error", "message": "Необходима авторизация"}
    try:
        result = await PaymentService(db).kaspi_test_top_up(user_id=current_user.id, amount=amount)
    except ServiceError as error:
        return {"status": "error", "message": error.message}
    return {
        "status": "success",
        "message": result.message,
        "balance": result.balance,
        "reference": result.reference,
    }


@router.post("/clubs/{club_id}/review")
async def submit_club_review(
    club_id: int,
    request: Request,
    rating: int = Form(...),
    comment: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    current_user = await get_current_user(request, db)
    if not current_user or not current_user.is_active:
        return RedirectResponse(url="/login", status_code=303)
    try:
        await ReviewService(db).submit_review(
            user_id=current_user.id, club_id=club_id, rating=rating, comment=comment
        )
    except ServiceError as error:
        return HTMLResponse(error.message, status_code=error.status_code)
    return RedirectResponse(url=f"/club/{club_id}#reviews", status_code=303)

@router.get("/user/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    current_user = await get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    res = await db.execute(
        select(models.Club)
        .options(selectinload(models.Club.games))
        .filter(models.Club.status == "active")
        .order_by(models.Club.city, models.Club.name)
    )
    clubs = res.scalars().all()
    stats = await club_card_stats(db, [club.id for club in clubs])
    return templates.TemplateResponse("user_dashboard.html", {
        "request": request,
        "clubs": clubs,
        "stats": stats,
        "current_user": current_user,
    })

@router.get("/club/{club_id}", response_class=HTMLResponse)
async def club_detail(club_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    current_user = await get_current_user(request, db)
    
    res_club = await db.execute(
        select(models.Club)
        .options(selectinload(models.Club.games))
        .filter(models.Club.id == club_id, models.Club.status == "active")
    )
    club = res_club.scalars().first()
    if not club:
        return HTMLResponse("Клуб не найден", status_code=404)

    res_comp = await db.execute(select(models.Computer).filter(models.Computer.club_id == club_id).order_by(models.Computer.number))
    computers = res_comp.scalars().all()
    res_prod = await db.execute(select(models.Product).filter(models.Product.club_id == club_id))
    products = res_prod.scalars().all()
    
    # Загружаем пакеты (тарифы) для этого клуба
    res_pkgs = await db.execute(select(models.Package).filter(models.Package.club_id == club_id))
    packages = res_pkgs.scalars().all()
    res_reviews = await db.execute(
        select(models.ClubReview)
        .options(selectinload(models.ClubReview.user))
        .filter(models.ClubReview.club_id == club_id)
        .order_by(models.ClubReview.updated_at.desc())
    )
    reviews = res_reviews.scalars().all()
    rating_avg = round(sum(review.rating for review in reviews) / len(reviews), 1) if reviews else 0
    current_user_review = next((review for review in reviews if current_user and review.user_id == current_user.id), None)

    return templates.TemplateResponse("club_detail.html", {
        "request": request,
        "club": club,
        "computers": computers,
        "products": products,
        "packages": packages,
        "reviews": reviews,
        "rating_avg": rating_avg,
        "current_user_review": current_user_review,
        "current_user": current_user,
        "kaspi_test_enabled": settings.enable_kaspi_test_payment,
    })
