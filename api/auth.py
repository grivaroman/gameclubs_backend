from fastapi import APIRouter, Depends, HTTPException, Request
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models
import schemas
from core.api_tokens import (
    access_token_expires_in_seconds,
    create_mobile_access_token,
    issue_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
)
from core.ratelimit import LOGIN_LIMIT, REGISTER_LIMIT, client_ip, enforce_rate_limit
from core.roles import ROLE_USER

router = APIRouter(tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def get_db():
    async with models.SessionLocal() as db:
        yield db


@router.post("/register")
async def register_user(request: Request, data: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    limited = await enforce_rate_limit(request, "api_register", REGISTER_LIMIT)
    if limited:
        return limited
    email = data.email.strip().lower()
    phone = data.phone.strip() if data.phone else None
    res = await db.execute(select(models.User).filter(models.User.email == email))
    if res.scalars().first():
        raise HTTPException(status_code=400, detail="Email уже занят")
    if phone:
        res_phone = await db.execute(select(models.User).filter(models.User.phone == phone))
        if res_phone.scalars().first():
            raise HTTPException(status_code=400, detail="Телефон уже занят")

    new_user = models.User(
        email=email,
        phone=phone,
        hashed_password=pwd_context.hash(data.password),
        role=ROLE_USER,
    )
    db.add(new_user)
    await db.commit()
    return {"message": "Регистрация успешна", "role": new_user.role}


@router.post("/login", response_model=schemas.TokenResponse)
async def api_login(request: Request, data: schemas.LoginRequest, db: AsyncSession = Depends(get_db)):
    limited = await enforce_rate_limit(request, "api_login", LOGIN_LIMIT)
    if limited:
        return limited
    email = data.email.strip().lower()
    res = await db.execute(select(models.User).filter(models.User.email == email))
    user = res.scalars().first()
    if not user or not user.is_active or not pwd_context.verify(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    refresh_raw = await issue_refresh_token(
        db, user, user_agent=request.headers.get("user-agent"), ip=client_ip(request),
    )
    tokens = schemas.TokenResponse(
        access_token=create_mobile_access_token(user.email),
        refresh_token=refresh_raw,
        expires_in=access_token_expires_in_seconds(),
        role=user.role,
    )
    await db.commit()
    return tokens


@router.post("/refresh", response_model=schemas.TokenResponse)
async def api_refresh(request: Request, data: schemas.RefreshRequest, db: AsyncSession = Depends(get_db)):
    result = await rotate_refresh_token(
        db, data.refresh_token, user_agent=request.headers.get("user-agent"), ip=client_ip(request),
    )
    if result is None:
        raise HTTPException(
            status_code=401, detail="Refresh-токен недействителен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user, new_refresh = result
    tokens = schemas.TokenResponse(
        access_token=create_mobile_access_token(user.email),
        refresh_token=new_refresh,
        expires_in=access_token_expires_in_seconds(),
        role=user.role,
    )
    await db.commit()
    return tokens


@router.post("/logout")
async def api_logout(data: schemas.LogoutRequest, db: AsyncSession = Depends(get_db)):
    """Отзывает переданный refresh-токен (идемпотентно)."""
    if data.refresh_token:
        await revoke_refresh_token(db, data.refresh_token)
        await db.commit()
    return {"message": "Выход выполнен"}
