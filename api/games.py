from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from schemas import GameResponse, GameCreate, MessageResponse
import models

router = APIRouter(prefix="/games", tags=["games"])

async def get_db():
    async with models.SessionLocal() as db:
        yield db

@router.get("", response_model=list[GameResponse])
async def get_games(db: AsyncSession = Depends(get_db)):
    """Получить список всех игр"""
    res = await db.execute(select(models.Game))
    games = res.scalars().all()
    return [GameResponse(id=g.id, name=g.name) for g in games]

@router.get("/{game_id}", response_model=GameResponse)
async def get_game(game_id: int, db: AsyncSession = Depends(get_db)):
    """Получить игру по ID"""
    res = await db.execute(select(models.Game).filter(models.Game.id == game_id))
    game = res.scalars().first()
    if not game:
        raise HTTPException(status_code=404, detail="Игра не найдена")
    return GameResponse(id=game.id, name=game.name)

@router.post("", response_model=GameResponse)
async def create_game(data: GameCreate, db: AsyncSession = Depends(get_db)):
    """Добавить новую игру"""
    res = await db.execute(select(models.Game).filter(models.Game.name == data.name))
    existing = res.scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Игра с таким названием уже существует")

    game = models.Game(name=data.name)
    db.add(game)
    await db.commit()
    await db.refresh(game)
    return GameResponse(id=game.id, name=game.name)

@router.delete("/{game_id}", response_model=MessageResponse)
async def delete_game(game_id: int, db: AsyncSession = Depends(get_db)):
    """Удалить игру"""
    res = await db.execute(select(models.Game).filter(models.Game.id == game_id))
    game = res.scalars().first()
    if not game:
        raise HTTPException(status_code=404, detail="Игра не найдена")
    await db.delete(game)
    await db.commit()
    return MessageResponse(success=True, message="Игра удалена")
