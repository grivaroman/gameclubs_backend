from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from passlib.context import CryptContext
import models, schemas

router = APIRouter(tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_db():
    db = models.SessionLocal()
    try: yield db
    finally: db.close()

@router.post("/register")
async def register_user(data: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email уже занят")
    
    hashed_pwd = pwd_context.hash(data.password)
    new_user = models.User(
        email=data.email,
        phone=data.phone,
        hashed_password=hashed_pwd,
        role=data.role
    )
    db.add(new_user)
    db.commit()
    return {"message": "Регистрация успешна", "role": new_user.role}