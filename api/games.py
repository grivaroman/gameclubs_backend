from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from schemas import GameResponse, GameCreate, MessageResponse
import models
from core.dependencies import get_current_user, get_db
from core.roles import ROLE_SUPERADMIN

router = APIRouter(prefix="/games", tags=["games"])


async def require_superadmin(request: Request, db: AsyncSession = Depends(get_db)) -> models.User:
    current_user = await get_current_user(request, db)
    if not current_user or current_user.role != ROLE_SUPERADMIN:
        raise HTTPException(status_code=403, detail="Доступно только суперадмину")
    return current_user


def normalize_game_name(name: str) -> str:
    return " ".join(name.strip().split())

@router.get("", response_model=list[GameResponse])
async def get_games(db: AsyncSession = Depends(get_db)):
    """Получить список всех игр"""
    res = await db.execute(select(models.Game).order_by(models.Game.name))
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
async def create_game(
    data: GameCreate,
    db: AsyncSession = Depends(get_db),
    _: models.User = Depends(require_superadmin),
):
    """Добавить новую игру"""
    name = normalize_game_name(data.name)
    if not name:
        raise HTTPException(status_code=400, detail="Название игры не может быть пустым")

    res = await db.execute(select(models.Game).filter(func.lower(models.Game.name) == name.lower()))
    existing = res.scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Игра с таким названием уже существует")

    game = models.Game(name=name)
    db.add(game)
    await db.commit()
    await db.refresh(game)
    return GameResponse(id=game.id, name=game.name)

@router.delete("/{game_id}", response_model=MessageResponse)
async def delete_game(
    game_id: int,
    db: AsyncSession = Depends(get_db),
    _: models.User = Depends(require_superadmin),
):
    """Удалить игру"""
    res = await db.execute(
        select(models.Game)
        .options(selectinload(models.Game.clubs))
        .filter(models.Game.id == game_id)
    )
    game = res.scalars().first()
    if not game:
        raise HTTPException(status_code=404, detail="Игра не найдена")
    game.clubs.clear()
    await db.delete(game)
    await db.commit()
    return MessageResponse(success=True, message="Игра удалена")
