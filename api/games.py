from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from schemas import GameResponse, GameCreate, MessageResponse
import models

router = APIRouter(prefix="/games", tags=["games"])

def get_db():
    db = models.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("", response_model=list[GameResponse])
async def get_games(db: Session = Depends(get_db)):
    """Получить список всех игр"""
    games = db.query(models.Game).all()
    return [GameResponse(id=g.id, name=g.name) for g in games]

@router.get("/{game_id}", response_model=GameResponse)
async def get_game(game_id: int, db: Session = Depends(get_db)):
    """Получить игру по ID"""
    game = db.query(models.Game).get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Игра не найдена")
    return GameResponse(id=game.id, name=game.name)

@router.post("", response_model=GameResponse)
async def create_game(data: GameCreate, db: Session = Depends(get_db)):
    """Добавить новую игру"""
    existing = db.query(models.Game).filter(models.Game.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Игра с таким названием уже существует")

    game = models.Game(name=data.name)
    db.add(game)
    db.commit()
    db.refresh(game)
    return GameResponse(id=game.id, name=game.name)

@router.delete("/{game_id}", response_model=MessageResponse)
async def delete_game(game_id: int, db: Session = Depends(get_db)):
    """Удалить игру"""
    game = db.query(models.Game).get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Игра не найдена")
    db.delete(game)
    db.commit()
    return MessageResponse(success=True, message="Игра удалена")
