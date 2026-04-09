from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from passlib.context import CryptContext
import models, schemas

router = APIRouter(tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def get_db():
    async with models.SessionLocal() as db:
        yield db

@router.post("/register")
async def register_user(data: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(models.User).filter(models.User.email == data.email))
    if res.scalars().first():
        raise HTTPException(status_code=400, detail="Email уже занят")
    
    hashed_pwd = pwd_context.hash(data.password)
    new_user = models.User(
        email=data.email,
        phone=data.phone,
        hashed_password=hashed_pwd,
        role=data.role
    )
    db.add(new_user)
    await db.commit()
    return {"message": "Регистрация успешна", "role": new_user.role}