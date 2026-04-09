from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

import models
from core.dependencies import templates, get_db, get_current_user

router = APIRouter(prefix="/admin", tags=["web_admin"])

@router.get("", response_class=HTMLResponse)
async def admin_page(request: Request, db: AsyncSession = Depends(get_db)):
    current_user = await get_current_user(request, db)
    if not current_user or current_user.role != "admin":
        return RedirectResponse(url="/login", status_code=303)

    res_clubs = await db.execute(select(models.Club))
    clubs = res_clubs.scalars().all()
    res_games = await db.execute(select(models.Game))
    all_games = res_games.scalars().all()
    res_orders = await db.execute(select(models.Order))
    orders = res_orders.scalars().all() 
    return templates.TemplateResponse("admin.html", {
        "request": request, 
        "clubs": clubs, 
        "all_games": all_games,
        "orders": orders
    })

@router.post("/add_club")
async def add_club(name: str = Form(...), address: str = Form(...), db: AsyncSession = Depends(get_db)):
    db.add(models.Club(name=name, address=address))
    await db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@router.post("/add_computers")
async def add_computers(
    club_id: int = Form(...), 
    count: int = Form(...), 
    category: str = Form(...), 
    db: AsyncSession = Depends(get_db)
):
    res_count = await db.execute(select(func.count(models.Computer.id)).filter(models.Computer.club_id == club_id))
    total_existing = res_count.scalar()
    
    for i in range(1, count + 1):
        new_pc = models.Computer(
            number=total_existing + i,
            category=category,
            club_id=club_id,
            status="free"
        )
        db.add(new_pc)
    
    await db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@router.post("/add_product")
async def add_product(
    club_id: int = Form(...), 
    name: str = Form(...), 
    price: int = Form(...), 
    image_url: str = Form(None),
    db: AsyncSession = Depends(get_db)
):
    db.add(models.Product(name=name, price=price, image_url=image_url, club_id=club_id))
    await db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@router.post("/add_game")
async def add_game(name: str = Form(...), db: AsyncSession = Depends(get_db)):
    db.add(models.Game(name=name))
    await db.commit()
    return RedirectResponse(url="/admin", status_code=303)
