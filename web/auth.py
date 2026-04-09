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

@router.post("/register")
async def register_action(
    email: str = Form(...), 
    password: str = Form(...), 
    role: str = Form(...),
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
        role=role,
        phone=phone
    )
    
    db.add(new_user)
    await db.commit()
    return RedirectResponse(url="/login", status_code=303)

@router.get("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="access_token")
    return response
