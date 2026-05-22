from datetime import timezone

from fastapi import Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from jose import JWTError, jwt
import models
from config import settings
from core.roles import is_valid_role

templates = Jinja2Templates(directory="templates")

async def get_db():
    async with models.SessionLocal() as db:
        yield db


def _token_revoked(user: models.User, payload: dict) -> bool:
    if user.tokens_invalid_before is None:
        return False
    iat = payload.get("iat")
    if iat is None:
        # У юзера выставлен cutoff, а токен старого формата без iat — считаем отозванным.
        return True
    invalid_before_ts = user.tokens_invalid_before.replace(tzinfo=timezone.utc).timestamp()
    return iat < invalid_before_ts


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        email: str = payload.get("sub")
        if email is None:
            return None
    except JWTError:
        return None
    res = await db.execute(select(models.User).filter(models.User.email == email))
    user = res.scalars().first()
    if user and not user.is_active:
        return None
    if user and not is_valid_role(user.role):
        return None
    if user and _token_revoked(user, payload):
        return None
    return user
