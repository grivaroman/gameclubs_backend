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
from core.roles import ROLE_ADMIN, ROLE_OWNER, ROLE_PENDING_OWNER, ROLE_SUPERADMIN, ROLE_USER

router = APIRouter(tags=["web_auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(email: str) -> str:
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    to_encode = {"sub": email, "exp": datetime.now(timezone.utc) + access_token_expires}
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

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
    
    if not user or not user.is_active or not pwd_context.verify(password, user.hashed_password):
        return HTMLResponse("Неверный логин или пароль", status_code=401)
    
    encoded_jwt = create_access_token(user.email)

    if user.role == ROLE_SUPERADMIN:
        response = RedirectResponse(url="/superadmin", status_code=303)
    elif user.role in (ROLE_ADMIN, ROLE_OWNER):
        response = RedirectResponse(url="/admin", status_code=303)
    elif user.role == ROLE_PENDING_OWNER:
        response = RedirectResponse(url="/owner/pending", status_code=303)
    else:
        response = RedirectResponse(url="/user/dashboard", status_code=303)
        
    response.set_cookie(
        key="access_token",
        value=encoded_jwt,
        httponly=True,
        max_age=settings.access_token_expire_minutes * 60,
        samesite="lax",
        secure=settings.cookie_secure,
    )
    return response

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@router.get("/owner/register", response_class=HTMLResponse)
async def owner_register_page(request: Request, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(models.Game).order_by(models.Game.name))
    all_games = res.scalars().all()
    return templates.TemplateResponse("owner_register.html", {"request": request, "all_games": all_games})

@router.get("/owner/pending", response_class=HTMLResponse)
async def owner_pending_page(request: Request):
    return templates.TemplateResponse("owner_pending.html", {"request": request})

@router.post("/register")
async def register_action(
    email: str = Form(...), 
    password: str = Form(...), 
    phone: str = Form(None),
    db: AsyncSession = Depends(get_db)
):
    email_clean = email.strip().lower()
    phone_clean = phone.strip() if phone else None
    res = await db.execute(select(models.User).filter(models.User.email == email_clean))
    existing = res.scalars().first()
    if existing:
        return HTMLResponse("Email уже занят", status_code=400)
    if phone_clean:
        res_phone = await db.execute(select(models.User).filter(models.User.phone == phone_clean))
        if res_phone.scalars().first():
            return HTMLResponse("Телефон уже занят", status_code=400)

    hashed_pwd = pwd_context.hash(password)
    new_user = models.User(
        email=email_clean,
        hashed_password=hashed_pwd,
        role=ROLE_USER,
        phone=phone_clean,
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
    phone_clean = phone.strip() if phone else None
    res = await db.execute(select(models.User).filter(models.User.email == email_clean))
    if res.scalars().first():
        return HTMLResponse("Email уже занят", status_code=400)
    if phone_clean:
        res_phone = await db.execute(select(models.User).filter(models.User.phone == phone_clean))
        if res_phone.scalars().first():
            return HTMLResponse("Телефон уже занят", status_code=400)

    owner = models.User(
        email=email_clean,
        hashed_password=pwd_context.hash(password),
        phone=phone_clean,
        role=ROLE_PENDING_OWNER,
    )
    db.add(owner)
    await db.flush()

    club = models.Club(
        name=club_name,
        city=city,
        address=address,
        photo_url=photo_url,
        contact_phone=phone_clean,
        description=description,
        amenities=amenities,
        working_hours=working_hours,
        owner_id=owner.id,
        status="pending",
    )
    for gid in game_ids:
        res_game = await db.execute(select(models.Game).filter(models.Game.id == gid))
        game = res_game.scalars().first()
        if game:
            club.games.append(game)
    db.add(club)
    await db.commit()

    encoded_jwt = create_access_token(owner.email)
    response = RedirectResponse(url="/owner/pending", status_code=303)
    response.set_cookie(
        key="access_token",
        value=encoded_jwt,
        httponly=True,
        max_age=settings.access_token_expire_minutes * 60,
        samesite="lax",
        secure=settings.cookie_secure,
    )
    return response

@router.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="access_token")
    return response
