from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta

import models
from core.dependencies import templates, get_db, get_current_user
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

@router.post("/book_seat/{pc_id}")
async def book_seat(
    request: Request, 
    pc_id: int, 
    package_id: int = Form(...), # Теперь нужно передать ID пакета
    db: AsyncSession = Depends(get_db)
):
    current_user = await get_current_user(request, db)
    if not current_user:
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

    # Получаем пакет
    res_pkg = await db.execute(select(models.Package).filter(models.Package.id == package_id))
    package = res_pkg.scalars().first()
    if not package:
        return {"status": "error", "message": "Тариф не найден"}

    # Проверка баланса
    if current_user.balance < package.price:
        return {"status": "error", "message": f"Недостаточно средств. Нужно {package.price}₸"}

    # Списываем деньги и ставим время
    current_user.balance -= package.price
    pc.status = "busy"
    pc.current_user_id = current_user.id
    pc.end_time = datetime.utcnow() + timedelta(minutes=package.duration_minutes)
    db.add(models.Booking(
        user_id=current_user.id,
        computer_id=pc.id,
        status="active",
        starts_at=datetime.utcnow(),
        ends_at=pc.end_time,
    ))
    db.add(models.Notification(
        kind="booking",
        club_id=pc.club_id,
        title="Новое бронирование",
        message=f"ПК #{pc.number} забронирован на {package.duration_minutes} мин.",
    ))
    
    await db.commit()
    # Отправляем команду разблокировки по WebSocket
    await manager.send_command(pc.id, {"command": "unlock", "user": current_user.email})
    
    return {"status": "success", "message": f"Бронирование на {package.duration_minutes} мин. успешно!"}

@router.post("/free_seat/{pc_id}")
async def free_seat(request: Request, pc_id: int, db: AsyncSession = Depends(get_db)):
    current_user = await get_current_user(request, db)
    if not current_user:
        return {"status": "error", "message": "Необходима авторизация"}

    res = await db.execute(select(models.Computer).filter(models.Computer.id == pc_id))
    pc = res.scalars().first()
    
    if not pc:
        return {"status": "error", "message": "Компьютер не найден"}
    
    if current_user.role != "admin" and pc.current_user_id != current_user.id:
        return {"status": "error", "message": "Вы не можете освободить чужое место"}

    pc.status = "free"
    pc.current_user_id = None
    pc.end_time = None
    await db.commit()
    # Отправляем команду блокировки по WebSocket
    await manager.send_command(pc.id, {"command": "lock"})
    
    return {"status": "success", "message": "Место успешно освобождено!"}

@router.post("/buy_product/{product_id}")
async def buy_product(request: Request, product_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return {"status": "error", "message": "Сначала зарегистрируйтесь или войдите"}

    res_prod = await db.execute(select(models.Product).filter(models.Product.id == product_id))
    product = res_prod.scalars().first()
    if not product:
        return {"status": "error", "message": "Товар не найден"}

    if user.balance < product.price:
        return {"status": "error", "message": "Недостаточно средств на балансе"}

    user.balance -= product.price
    new_order = models.Order(user_id=user.id, product_id=product_id, status="new")
    db.add(new_order)
    db.add(models.Notification(
        kind="order",
        club_id=product.club_id,
        title="Новый заказ",
        message=f"Заказали товар: {product.name}.",
    ))
    await db.commit()
    return {"status": "success", "message": f"Заказ принят! Списано {product.price}₸"}

@router.get("/user/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    current_user = await get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    res = await db.execute(select(models.Club).options(selectinload(models.Club.games)).order_by(models.Club.city, models.Club.name))
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
        .filter(models.Club.id == club_id)
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
