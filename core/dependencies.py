from fastapi import Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from jose import JWTError, jwt
import models
from config import settings

templates = Jinja2Templates(directory="templates")

async def get_db():
    async with models.SessionLocal() as db:
        yield db

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
    return res.scalars().first()
