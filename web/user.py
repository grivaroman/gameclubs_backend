from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta

import models
from core.dependencies import templates, get_db, get_current_user
from core.finance import debit_user_balance
from core.fraud import evaluate_admin_pc_override, evaluate_booking_success, evaluate_failed_payment, evaluate_order_success
from core.roles import CLUB_ADMIN_ROLES, ROLE_SUPERADMIN
from core.ws import manager

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
        stats[club_id] = {
            "total": len(computers),
            "free": len([pc for pc in computers if pc.status == "free"]),
            "busy": len([pc for pc in computers if pc.status == "busy"]),
            "products": len(products),
        }
    return stats


async def user_can_manage_club(db: AsyncSession, user: models.User, club_id: int) -> bool:
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


async def send_pc_command(pc_id: int, message: dict):
    try:
        await manager.send_command(pc_id, message)
    except Exception:
        pass


async def lock_current_user(db: AsyncSession, user_id: int):
    res = await db.execute(
        select(models.User)
        .filter(models.User.id == user_id, models.User.is_active == 1)
        .with_for_update()
    )
    return res.scalars().first()

@router.post("/book_seat/{pc_id}")
async def book_seat(
    request: Request, 
    pc_id: int, 
    package_id: int = Form(...), # Теперь нужно передать ID пакета
    db: AsyncSession = Depends(get_db)
):
    current_user = await get_current_user(request, db)
    if not current_user or not current_user.is_active:
        return {"status": "error", "message": "Необходима авторизация"}

    user = await lock_current_user(db, current_user.id)
    if not user:
        return {"status": "error", "message": "Необходима авторизация"}

    # Блокируем запись ПК для предотвращения Race Condition
    res = await db.execute(
        select(models.Computer).filter(models.Computer.id == pc_id).with_for_update()
    )
    pc = res.scalars().first()
    
    if not pc:
        return {"status": "error", "message": "Компьютер не найден"}
    
    if pc.status != "free":
        return {"status": "error", "message": "Место уже занято"}

    res_club = await db.execute(
        select(models.Club).filter(
            models.Club.id == pc.club_id,
            models.Club.status == "active",
        )
    )
    club = res_club.scalars().first()
    if not club:
        return {"status": "error", "message": "Клуб сейчас недоступен для бронирования"}

    # Получаем пакет
    res_pkg = await db.execute(
        select(models.Package).filter(
            models.Package.id == package_id,
            models.Package.club_id == pc.club_id,
        )
    )
    package = res_pkg.scalars().first()
    if not package:
        return {"status": "error", "message": "Тариф не найден"}
    if package.pc_category != pc.category:
        return {"status": "error", "message": "Тариф не подходит для выбранного ПК"}
    if package.price < 0 or package.duration_minutes < 1:
        return {"status": "error", "message": "Тариф настроен некорректно"}

    # Проверка баланса
    if user.balance < package.price:
        await evaluate_failed_payment(
            db,
            user=user,
            event_type="player_booking_insufficient_funds",
            amount=package.price,
            balance=user.balance,
            club_id=pc.club_id,
        )
        await db.commit()
        return {"status": "error", "message": f"Недостаточно средств. Нужно {package.price}₸"}

    # Списываем деньги и ставим время
    pc.status = "busy"
    pc.current_user_id = user.id
    pc.end_time = datetime.utcnow() + timedelta(minutes=package.duration_minutes)
    booking = models.Booking(
        user_id=user.id,
        computer_id=pc.id,
        amount_paid=package.price,
        status="active",
        starts_at=datetime.utcnow(),
        ends_at=pc.end_time,
    )
    db.add(booking)
    await db.flush()
    await debit_user_balance(
        db,
        user=user,
        amount=package.price,
        kind="booking_debit",
        club_id=pc.club_id,
        booking_id=booking.id,
        reason="Бронирование ПК",
        metadata={"pc_id": pc.id, "package_id": package.id, "duration_minutes": package.duration_minutes},
    )
    db.add(models.Notification(
        kind="booking",
        club_id=pc.club_id,
        title="Новое бронирование",
        message=f"ПК #{pc.number} забронирован на {package.duration_minutes} мин.",
    ))
    await evaluate_booking_success(db, user=user, pc=pc, package=package)
    
    await db.commit()
    # Отправляем команду разблокировки по WebSocket
    await send_pc_command(pc.id, {"command": "unlock", "user": user.email})
    
    return {"status": "success", "message": f"Бронирование на {package.duration_minutes} мин. успешно!"}

@router.post("/free_seat/{pc_id}")
async def free_seat(request: Request, pc_id: int, db: AsyncSession = Depends(get_db)):
    current_user = await get_current_user(request, db)
    if not current_user or not current_user.is_active:
        return {"status": "error", "message": "Необходима авторизация"}

    res = await db.execute(select(models.Computer).filter(models.Computer.id == pc_id))
    pc = res.scalars().first()
    
    if not pc:
        return {"status": "error", "message": "Компьютер не найден"}
    
    can_manage = await user_can_manage_club(db, current_user, pc.club_id)
    if not can_manage and pc.current_user_id != current_user.id:
        return {"status": "error", "message": "Вы не можете освободить чужое место"}

    if can_manage:
        await evaluate_admin_pc_override(db, admin=current_user, pc=pc, new_status="free")

    pc.status = "free"
    pc.current_user_id = None
    pc.end_time = None
    await db.execute(
        update(models.Booking)
        .filter(models.Booking.computer_id == pc.id, models.Booking.status == "active")
        .values(status="completed")
    )
    await db.commit()
    # Отправляем команду блокировки по WebSocket
    await send_pc_command(pc.id, {"command": "lock"})
    
    return {"status": "success", "message": "Место успешно освобождено!"}

@router.post("/buy_product/{product_id}")
async def buy_product(request: Request, product_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user or not user.is_active:
        return {"status": "error", "message": "Сначала зарегистрируйтесь или войдите"}

    user = await lock_current_user(db, user.id)
    if not user:
        return {"status": "error", "message": "Сначала зарегистрируйтесь или войдите"}

    res_prod = await db.execute(select(models.Product).filter(models.Product.id == product_id))
    product = res_prod.scalars().first()
    if not product:
        return {"status": "error", "message": "Товар не найден"}

    res_club = await db.execute(
        select(models.Club.id).filter(
            models.Club.id == product.club_id,
            models.Club.status == "active",
        )
    )
    if not res_club.scalars().first():
        return {"status": "error", "message": "Клуб сейчас недоступен для заказов"}
    if product.price < 0:
        return {"status": "error", "message": "Товар настроен некорректно"}

    if user.balance < product.price:
        await evaluate_failed_payment(
            db,
            user=user,
            event_type="player_order_insufficient_funds",
            amount=product.price,
            balance=user.balance,
            club_id=product.club_id,
        )
        await db.commit()
        return {"status": "error", "message": "Недостаточно средств на балансе"}

    new_order = models.Order(user_id=user.id, product_id=product_id, amount_paid=product.price, status="new")
    db.add(new_order)
    await db.flush()
    await debit_user_balance(
        db,
        user=user,
        amount=product.price,
        kind="order_debit",
        club_id=product.club_id,
        order_id=new_order.id,
        reason="Покупка товара",
        metadata={"product_id": product.id},
    )
    db.add(models.Notification(
        kind="order",
        club_id=product.club_id,
        title="Новый заказ",
        message=f"Заказали товар: {product.name}.",
    ))
    await evaluate_order_success(db, user=user, product=product)
    await db.commit()
    return {"status": "success", "message": f"Заказ принят! Списано {product.price}₸"}

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

    return templates.TemplateResponse("club_detail.html", {
        "request": request, 
        "club": club, 
        "computers": computers, 
        "products": products,
        "packages": packages,
        "current_user": current_user
    })
