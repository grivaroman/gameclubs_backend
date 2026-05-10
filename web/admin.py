import csv
import io
import json
import os
import urllib.error
import urllib.request

from fastapi import APIRouter, Body, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

import models
from core.dependencies import get_current_user, get_db, templates

router = APIRouter(prefix="/admin", tags=["web_admin"])


async def create_notification(db: AsyncSession, kind: str, title: str, message: str, club_id=None):
    db.add(models.Notification(kind=kind, title=title, message=message, club_id=club_id))


async def get_owner_clubs(db: AsyncSession, owner: models.User):
    res = await db.execute(select(models.Club).filter(models.Club.owner_id == owner.id))
    clubs = res.scalars().all()
    if clubs:
        return clubs

    res = await db.execute(select(models.Club).filter(models.Club.owner_id.is_(None)))
    return res.scalars().all()


async def owner_club_ids(db: AsyncSession, owner: models.User):
    return [club.id for club in await get_owner_clubs(db, owner)]


async def ensure_owner_club(db: AsyncSession, owner: models.User, club_id: int):
    return club_id in await owner_club_ids(db, owner)


def parse_products_file(upload: UploadFile, payload: bytes):
    filename = (upload.filename or "").lower()
    if filename.endswith(".csv"):
        rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
    elif filename.endswith(".xlsx"):
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(payload), read_only=True, data_only=True)
        sheet = workbook.active
        values = list(sheet.iter_rows(values_only=True))
        headers = [str(cell).strip() if cell is not None else "" for cell in values[0]] if values else []
        rows = [dict(zip(headers, row)) for row in values[1:]]
    else:
        raise ValueError("Поддерживаются только CSV и XLSX файлы")

    products = []
    for row in rows:
        normalized = {str(k).strip().lower(): v for k, v in row.items() if k}
        name = normalized.get("name") or normalized.get("название") or normalized.get("товар")
        price = normalized.get("price") or normalized.get("цена")
        image_url = normalized.get("image_url") or normalized.get("картинка") or normalized.get("фото") or ""
        if not name or price in (None, ""):
            continue
        try:
            price_int = int(float(str(price).replace(",", ".")))
        except ValueError:
            continue
        products.append({
            "name": str(name).strip(),
            "price": price_int,
            "image_url": str(image_url).strip() if image_url else None,
        })
    return products


async def build_admin_ai_context(db: AsyncSession, club_ids: list[int]):
    clubs_count = len(club_ids)
    computers = []
    orders_count = 0
    active_bookings = 0
    if club_ids:
        res = await db.execute(select(models.Computer).filter(models.Computer.club_id.in_(club_ids)))
        computers = res.scalars().all()
        res_orders = await db.execute(
            select(func.count(models.Order.id))
            .join(models.Product)
            .filter(models.Product.club_id.in_(club_ids))
        )
        orders_count = res_orders.scalar() or 0
        res_bookings = await db.execute(
            select(func.count(models.Booking.id))
            .join(models.Computer)
            .filter(models.Computer.club_id.in_(club_ids), models.Booking.status == "active")
        )
        active_bookings = res_bookings.scalar() or 0

    free_count = len([pc for pc in computers if pc.status == "free"])
    busy_count = len([pc for pc in computers if pc.status == "busy"])
    return (
        "Проект: CyberBooking, FastAPI async + SQLAlchemy + Jinja2. "
        "Сущности: User, Club, Game, Computer, Product, Order, Booking, Notification. "
        f"Клубов владельца {clubs_count}, ПК {len(computers)}, свободно {free_count}, "
        f"занято {busy_count}, заказов {orders_count}, активных броней {active_bookings}."
    )


@router.get("", response_class=HTMLResponse)
async def admin_page(request: Request, db: AsyncSession = Depends(get_db)):
    current_user = await get_current_user(request, db)
    if not current_user or current_user.role not in ("admin", "owner"):
        return RedirectResponse(url="/login", status_code=303)

    clubs = await get_owner_clubs(db, current_user)
    club_ids = [club.id for club in clubs]

    res_games = await db.execute(select(models.Game).order_by(models.Game.name))
    all_games = res_games.scalars().all()

    orders = []
    computers = []
    products = []
    notifications = []
    if club_ids:
        res_orders = await db.execute(
            select(models.Order)
            .options(selectinload(models.Order.user), selectinload(models.Order.product))
            .join(models.Product)
            .filter(models.Product.club_id.in_(club_ids))
            .order_by(models.Order.created_at.desc())
        )
        orders = res_orders.scalars().all()

        res_computers = await db.execute(
            select(models.Computer)
            .filter(models.Computer.club_id.in_(club_ids))
            .order_by(models.Computer.club_id, models.Computer.number)
        )
        computers = res_computers.scalars().all()

        res_products = await db.execute(
            select(models.Product)
            .options(selectinload(models.Product.club))
            .filter(models.Product.club_id.in_(club_ids))
            .order_by(models.Product.id.desc())
        )
        products = res_products.scalars().all()

        res_notifications = await db.execute(
            select(models.Notification)
            .filter(or_(models.Notification.club_id.in_(club_ids), models.Notification.club_id.is_(None)))
            .order_by(models.Notification.created_at.desc())
            .limit(15)
        )
        notifications = res_notifications.scalars().all()

    total_pcs = len(computers)
    free_pcs = len([pc for pc in computers if pc.status == "free"])
    busy_pcs = len([pc for pc in computers if pc.status == "busy"])
    reserved_pcs = len([pc for pc in computers if pc.status == "reserved"])
    analytics = {
        "clubs": len(clubs),
        "products": len(products),
        "orders": len(orders),
        "total_pcs": total_pcs,
        "free_pcs": free_pcs,
        "busy_pcs": busy_pcs,
        "reserved_pcs": reserved_pcs,
        "occupancy": round((busy_pcs + reserved_pcs) / total_pcs * 100) if total_pcs else 0,
        "unread_notifications": len([n for n in notifications if not n.is_read]),
    }

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "clubs": clubs,
        "all_games": all_games,
        "orders": orders,
        "computers": computers,
        "products": products,
        "notifications": notifications,
        "analytics": analytics,
        "owner": current_user,
    })


@router.post("/add_club")
async def add_club(
    request: Request,
    name: str = Form(...),
    address: str = Form(...),
    city: str = Form(""),
    photo_url: str = Form(None),
    description: str = Form(""),
    amenities: str = Form(""),
    contact_phone: str = Form(None),
    working_hours: str = Form("24/7"),
    game_ids: list[int] = Form([]),
    db: AsyncSession = Depends(get_db),
):
    current_user = await get_current_user(request, db)
    if not current_user or current_user.role not in ("admin", "owner"):
        return RedirectResponse(url="/login", status_code=303)

    club = models.Club(
        name=name,
        address=address,
        city=city,
        photo_url=photo_url,
        description=description,
        amenities=amenities,
        contact_phone=contact_phone,
        working_hours=working_hours,
        owner_id=current_user.id,
    )
    for gid in game_ids:
        res = await db.execute(select(models.Game).filter(models.Game.id == gid))
        game = res.scalars().first()
        if game:
            club.games.append(game)
    db.add(club)
    await db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/add_computers")
async def add_computers(
    request: Request,
    club_id: int = Form(...),
    count: int = Form(...),
    category: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    current_user = await get_current_user(request, db)
    if not current_user or not await ensure_owner_club(db, current_user, club_id):
        return HTMLResponse("Нет доступа к этому клубу", status_code=403)

    res_count = await db.execute(select(func.count(models.Computer.id)).filter(models.Computer.club_id == club_id))
    total_existing = res_count.scalar() or 0
    for i in range(1, count + 1):
        db.add(models.Computer(number=total_existing + i, category=category, club_id=club_id, status="free"))
    await create_notification(db, "computer", "ПК добавлены", f"Добавлено {count} ПК категории {category}.", club_id)
    await db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/add_computer")
async def add_computer(
    request: Request,
    club_id: int = Form(...),
    number: int = Form(...),
    category: str = Form(...),
    status: str = Form("free"),
    position_x: int = Form(0),
    position_y: int = Form(0),
    db: AsyncSession = Depends(get_db),
):
    current_user = await get_current_user(request, db)
    if not current_user or not await ensure_owner_club(db, current_user, club_id):
        return HTMLResponse("Нет доступа к этому клубу", status_code=403)

    db.add(models.Computer(
        number=number,
        category=category,
        status=status,
        club_id=club_id,
        position_x=position_x,
        position_y=position_y,
    ))
    await create_notification(db, "computer", "ПК подключен", f"ПК #{number} добавлен через админ-панель.", club_id)
    await db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/update_computer_status")
async def update_computer_status(
    request: Request,
    pc_id: int = Form(...),
    status: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    current_user = await get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)
    res = await db.execute(select(models.Computer).filter(models.Computer.id == pc_id))
    pc = res.scalars().first()
    if pc and not await ensure_owner_club(db, current_user, pc.club_id):
        return HTMLResponse("Нет доступа к этому клубу", status_code=403)
    if pc:
        pc.status = status
        await create_notification(db, "computer", "Статус ПК изменен", f"ПК #{pc.number}: {status}.", pc.club_id)
        await db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/add_product")
async def add_product(
    request: Request,
    club_id: int = Form(...),
    name: str = Form(...),
    price: int = Form(...),
    image_url: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    current_user = await get_current_user(request, db)
    if not current_user or not await ensure_owner_club(db, current_user, club_id):
        return HTMLResponse("Нет доступа к этому клубу", status_code=403)
    db.add(models.Product(name=name, price=price, image_url=image_url, club_id=club_id))
    await create_notification(db, "import", "Товар добавлен", f"{name} добавлен в магазин.", club_id)
    await db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/import_products")
async def import_products(
    request: Request,
    club_id: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    current_user = await get_current_user(request, db)
    if not current_user or not await ensure_owner_club(db, current_user, club_id):
        return HTMLResponse("Нет доступа к этому клубу", status_code=403)
    try:
        products = parse_products_file(file, await file.read())
    except ValueError as exc:
        return HTMLResponse(str(exc), status_code=400)
    for product in products:
        db.add(models.Product(club_id=club_id, **product))
    await create_notification(db, "import", "Импорт товаров", f"Загружено товаров: {len(products)}.", club_id)
    await db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/add_game")
async def add_game(name: str = Form(...), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(models.Game).filter(models.Game.name == name))
    if not res.scalars().first():
        db.add(models.Game(name=name))
        await db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/complete_order/{order_id}")
async def complete_order(order_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(models.Order).filter(models.Order.id == order_id))
    order = res.scalars().first()
    if order:
        order.status = "completed"
        await db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/top_up_balance")
async def top_up_balance(user_id: int = Form(...), amount: int = Form(...), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(models.User).filter(models.User.id == user_id))
    user = res.scalars().first()
    if user:
        user.balance += amount
        await db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/add_package")
async def add_package(
    club_id: int = Form(...),
    name: str = Form(...),
    price: int = Form(...),
    duration: int = Form(...),
    category: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    db.add(models.Package(name=name, price=price, duration_minutes=duration, pc_category=category, club_id=club_id))
    await db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/ai_chat")
async def admin_ai_chat(request: Request, payload: dict = Body(...), db: AsyncSession = Depends(get_db)):
    current_user = await get_current_user(request, db)
    if not current_user or current_user.role not in ("admin", "owner"):
        return JSONResponse({"answer": "Сначала войди как владелец клуба."}, status_code=401)

    question = (payload.get("message") or "").strip()
    if not question:
        return JSONResponse({"answer": "Напиши вопрос по проекту или админке."})

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return JSONResponse({
            "answer": "GROQ_API_KEY не настроен на сервере. Добавь ключ в переменные окружения и перезапусти приложение."
        }, status_code=503)

    club_ids = await owner_club_ids(db, current_user)
    body = {
        "model": os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        "messages": [
            {"role": "system", "content": "Ты AI-помощник администратора CyberBooking. Отвечай по-русски, кратко и практично."},
            {"role": "system", "content": await build_admin_ai_context(db, club_ids)},
            {"role": "user", "content": question},
        ],
        "temperature": 0.3,
        "max_tokens": 700,
    }
    groq_request = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(groq_request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return JSONResponse({"answer": exc.read().decode("utf-8", errors="ignore")}, status_code=502)
    except urllib.error.URLError as exc:
        return JSONResponse({"answer": f"Не удалось подключиться к Groq: {exc.reason}"}, status_code=502)

    answer = data.get("choices", [{}])[0].get("message", {}).get("content", "Ответ не получен.")
    return JSONResponse({"answer": answer})
