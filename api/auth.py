from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models
import schemas
from config import settings
from core.ratelimit import LOGIN_LIMIT, REGISTER_LIMIT, enforce_rate_limit
from core.roles import ROLE_USER

router = APIRouter(tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def get_db():
    async with models.SessionLocal() as db:
        yield db


def _create_access_token(email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "iat": int(now.timestamp()),
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


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
async def api_login(
    request: Request,
    data: schemas.LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    limited = await enforce_rate_limit(request, "api_login", LOGIN_LIMIT)
    if limited:
        return limited
    email = data.email.strip().lower()
    res = await db.execute(select(models.User).filter(models.User.email == email))
    user = res.scalars().first()
    if not user or not user.is_active or not pwd_context.verify(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    token = _create_access_token(user.email)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=settings.access_token_expire_minutes * 60,
        samesite="lax",
        secure=settings.cookie_secure,
    )
    return schemas.TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
        role=user.role,
    )


@router.post("/logout")
async def api_logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Выход выполнен"}
