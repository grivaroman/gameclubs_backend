from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta, timezone

import models
from config import settings
from core.dependencies import templates, get_db

router = APIRouter(tags=["web_auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
async def login_action(
    email: str = Form(...), 
    password: str = Form(...), 
    db: AsyncSession = Depends(get_db)
):
    email_clean = email.strip().lower()
    res = await db.execute(select(models.User).filter(models.User.email == email_clean))
    user = res.scalars().first()
    
    if not user or not pwd_context.verify(password, user.hashed_password):
        return HTMLResponse("Неверный логин или пароль", status_code=401)
    
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    to_encode = {"sub": user.email, "exp": datetime.now(timezone.utc) + access_token_expires}
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

    if user.role == "admin":
        response = RedirectResponse(url="/admin", status_code=303)
    else:
        response = RedirectResponse(url="/user/dashboard", status_code=303)
        
    response.set_cookie(key="access_token", value=encoded_jwt, httponly=True, max_age=settings.access_token_expire_minutes * 60)
    return response

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@router.get("/owner/register", response_class=HTMLResponse)
async def owner_register_page(request: Request, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(models.Game).order_by(models.Game.name))
    all_games = res.scalars().all()
    return templates.TemplateResponse("owner_register.html", {"request": request, "all_games": all_games})

@router.post("/register")
async def register_action(
    email: str = Form(...), 
    password: str = Form(...), 
    phone: str = Form(None),
    db: AsyncSession = Depends(get_db)
):
    email_clean = email.strip().lower()
    res = await db.execute(select(models.User).filter(models.User.email == email_clean))
    existing = res.scalars().first()
    if existing:
        return HTMLResponse("Email уже занят", status_code=400)

    hashed_pwd = pwd_context.hash(password)
    new_user = models.User(
        email=email_clean,
        hashed_password=hashed_pwd,
        role="user",
        phone=phone
    )
    
    db.add(new_user)
    await db.commit()
    return RedirectResponse(url="/login", status_code=303)

@router.post("/owner/register")
async def owner_register_action(
    email: str = Form(...),
    password: str = Form(...),
    phone: str = Form(None),
    club_name: str = Form(...),
    city: str = Form(""),
    address: str = Form(...),
    photo_url: str = Form(None),
    description: str = Form(""),
    amenities: str = Form(""),
    working_hours: str = Form("24/7"),
    game_ids: list[int] = Form([]),
    db: AsyncSession = Depends(get_db)
):
    email_clean = email.strip().lower()
    res = await db.execute(select(models.User).filter(models.User.email == email_clean))
    if res.scalars().first():
        return HTMLResponse("Email уже занят", status_code=400)

    owner = models.User(
        email=email_clean,
        hashed_password=pwd_context.hash(password),
        phone=phone,
        role="admin",
    )
    db.add(owner)
    await db.flush()

    club = models.Club(
        name=club_name,
        city=city,
        address=address,
        photo_url=photo_url,
        contact_phone=phone,
        description=description,
        amenities=amenities,
        working_hours=working_hours,
        owner_id=owner.id,
    )
    for gid in game_ids:
        res_game = await db.execute(select(models.Game).filter(models.Game.id == gid))
        game = res_game.scalars().first()
        if game:
            club.games.append(game)
    db.add(club)
    await db.commit()

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    to_encode = {"sub": owner.email, "exp": datetime.now(timezone.utc) + access_token_expires}
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    response = RedirectResponse(url="/admin", status_code=303)
    response.set_cookie(key="access_token", value=encoded_jwt, httponly=True, max_age=settings.access_token_expire_minutes * 60)
    return response

@router.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="access_token")
    return response
