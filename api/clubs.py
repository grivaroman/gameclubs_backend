from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from schemas import (
    ClubResponse, ClubCreate, ClubListResponse,
    GameResponse, PackageResponse, MessageResponse
)
import models

router = APIRouter(prefix="/clubs", tags=["clubs"])

def get_db():
    db = models.SessionLocal()
    try:
        yield db
    finally:
        db.close()

def club_to_response(club: models.Club) -> ClubResponse:
    """Преобразовать модель клуба в response схему"""
    return ClubResponse(
        id=club.id,
        name=club.name,
        address=club.address,
        description=club.description,
        amenities=club.amenities,
        games=[GameResponse(id=g.id, name=g.name) for g in club.games],
        packages=[
            PackageResponse(id=p.id, name=p.name, price=p.price, pc_category=p.pc_category)
            for p in club.packages
        ]
    )

@router.get("", response_model=list[ClubListResponse])
async def get_clubs(db: Session = Depends(get_db)):
    """Получить список всех клубов (краткая информация)"""
    clubs = db.query(models.Club).all()
    return [
        ClubListResponse(
            id=c.id,
            name=c.name,
            address=c.address,
            description=c.description
        ) for c in clubs
    ]

@router.get("/{club_id}", response_model=ClubResponse)
async def get_club(club_id: int, db: Session = Depends(get_db)):
    """Получить полную информацию о клубе по ID"""
    club = db.query(models.Club).get(club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Клуб не найден")
    return club_to_response(club)

@router.post("", response_model=ClubResponse)
async def create_club(data: ClubCreate, db: Session = Depends(get_db)):
    """Создать новый клуб"""
    new_club = models.Club(
        name=data.name,
        address=data.address,
        description=data.description,
        amenities=data.amenities
    )

    # Добавить игры
    for gid in data.game_ids:
        game = db.query(models.Game).get(gid)
        if game:
            new_club.games.append(game)

    db.add(new_club)
    db.flush()

    # Добавить пакеты
    for pkg in data.packages:
        new_pkg = models.Package(
            name=pkg.name,
            price=pkg.price,
            pc_category=pkg.pc_category,
            club_id=new_club.id
        )
        db.add(new_pkg)

    db.commit()
    db.refresh(new_club)
    return club_to_response(new_club)

@router.put("/{club_id}", response_model=ClubResponse)
async def update_club(club_id: int, data: ClubCreate, db: Session = Depends(get_db)):
    """Обновить информацию о клубе"""
    club = db.query(models.Club).get(club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Клуб не найден")

    club.name = data.name
    club.address = data.address
    club.description = data.description
    club.amenities = data.amenities

    # Обновить игры
    club.games.clear()
    for gid in data.game_ids:
        game = db.query(models.Game).get(gid)
        if game:
            club.games.append(game)

    # Удалить старые пакеты и добавить новые
    for pkg in club.packages:
        db.delete(pkg)

    for pkg in data.packages:
        new_pkg = models.Package(
            name=pkg.name,
            price=pkg.price,
            pc_category=pkg.pc_category,
            club_id=club.id
        )
        db.add(new_pkg)

    db.commit()
    db.refresh(club)
    return club_to_response(club)

@router.delete("/{club_id}", response_model=MessageResponse)
async def delete_club(club_id: int, db: Session = Depends(get_db)):
    """Удалить клуб"""
    club = db.query(models.Club).get(club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Клуб не найден")
    db.delete(club)
    db.commit()
    return MessageResponse(success=True, message="Клуб удален")
