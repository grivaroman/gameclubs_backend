from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models
from core.dependencies import templates, get_db, get_current_user

router = APIRouter(tags=["web_user"])

@router.post("/book_seat/{pc_id}")
async def book_seat(request: Request, pc_id: int, db: AsyncSession = Depends(get_db)):
    current_user = await get_current_user(request, db)
    if not current_user:
        return {"status": "error", "message": "Необходима авторизация"}

    res = await db.execute(select(models.Computer).filter(models.Computer.id == pc_id))
    pc = res.scalars().first()
    
    if not pc:
        return {"status": "error", "message": "Компьютер не найден"}
    
    if pc.status != "free":
        return {"status": "error", "message": "Место уже занято"}

    pc.status = "busy"
    pc.current_user_id = current_user.id
    await db.commit()
    return {"status": "success", "message": "Забронировано!"}

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
    await db.commit()
    return {"status": "success", "message": "Место успешно освобождено!"}

@router.post("/buy_product/{product_id}")
async def buy_product(request: Request, product_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return {"status": "error", "message": "Сначала зарегистрируйтесь или войдите"}
        
    new_order = models.Order(user_id=user.id, product_id=product_id, status="new")
    db.add(new_order)
    await db.commit()
    return {"status": "success", "message": "Заказ принят, ожидайте доставку к компу!"}

@router.get("/user/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    current_user = await get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    res = await db.execute(select(models.Club))
    clubs = res.scalars().all()
    return templates.TemplateResponse("user_dashboard.html", {"request": request, "clubs": clubs, "current_user": current_user})

@router.get("/club/{club_id}", response_class=HTMLResponse)
async def club_detail(club_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    current_user = await get_current_user(request, db)
    
    res_club = await db.execute(select(models.Club).filter(models.Club.id == club_id))
    club = res_club.scalars().first()
    if not club:
        return HTMLResponse("Клуб не найден", status_code=404)

    res_comp = await db.execute(select(models.Computer).filter(models.Computer.club_id == club_id).order_by(models.Computer.number))
    computers = res_comp.scalars().all()
    res_prod = await db.execute(select(models.Product).filter(models.Product.club_id == club_id))
    products = res_prod.scalars().all()

    return templates.TemplateResponse("club_detail.html", {
        "request": request, 
        "club": club, 
        "computers": computers, 
        "products": products,
        "current_user": current_user
    })
