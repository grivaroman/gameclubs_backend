from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from schemas import (
    ClubResponse, ClubCreate, ClubListResponse,
    GameResponse, PackageResponse, MessageResponse
)
import models

router = APIRouter(prefix="/clubs", tags=["clubs"])

async def get_db():
    async with models.SessionLocal() as db:
        yield db

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
async def get_clubs(db: AsyncSession = Depends(get_db)):
    """Получить список всех клубов (краткая информация)"""
    res = await db.execute(select(models.Club))
    clubs = res.scalars().all()
    return [
        ClubListResponse(
            id=c.id,
            name=c.name,
            address=c.address,
            description=c.description
        ) for c in clubs
    ]

@router.get("/{club_id}", response_model=ClubResponse)
async def get_club(club_id: int, db: AsyncSession = Depends(get_db)):
    """Получить полную информацию о клубе по ID"""
    res = await db.execute(select(models.Club).filter(models.Club.id == club_id))
    club = res.scalars().first()
    if not club:
        raise HTTPException(status_code=404, detail="Клуб не найден")
    return club_to_response(club)

@router.post("", response_model=ClubResponse)
async def create_club(data: ClubCreate, db: AsyncSession = Depends(get_db)):
    """Создать новый клуб"""
    new_club = models.Club(
        name=data.name,
        address=data.address,
        description=data.description,
        amenities=data.amenities
    )

    # Добавить игры
    for gid in data.game_ids:
        res = await db.execute(select(models.Game).filter(models.Game.id == gid))
        game = res.scalars().first()
        if game:
            new_club.games.append(game)

    db.add(new_club)
    await db.flush()

    # Добавить пакеты
    for pkg in data.packages:
        new_pkg = models.Package(
            name=pkg.name,
            price=pkg.price,
            pc_category=pkg.pc_category,
            club_id=new_club.id
        )
        db.add(new_pkg)

    await db.commit()
    await db.refresh(new_club)
    return club_to_response(new_club)

@router.put("/{club_id}", response_model=ClubResponse)
async def update_club(club_id: int, data: ClubCreate, db: AsyncSession = Depends(get_db)):
    """Обновить информацию о клубе"""
    res = await db.execute(select(models.Club).filter(models.Club.id == club_id))
    club = res.scalars().first()
    if not club:
        raise HTTPException(status_code=404, detail="Клуб не найден")

    club.name = data.name
    club.address = data.address
    club.description = data.description
    club.amenities = data.amenities

    # Обновить игры
    club.games.clear()
    for gid in data.game_ids:
        res = await db.execute(select(models.Game).filter(models.Game.id == gid))
        game = res.scalars().first()
        if game:
            club.games.append(game)

    # Удалить старые пакеты и добавить новые
    for pkg in club.packages:
        await db.delete(pkg)

    for pkg in data.packages:
        new_pkg = models.Package(
            name=pkg.name,
            price=pkg.price,
            pc_category=pkg.pc_category,
            club_id=club.id
        )
        db.add(new_pkg)

    await db.commit()
    await db.refresh(club)
    return club_to_response(club)

@router.delete("/{club_id}", response_model=MessageResponse)
async def delete_club(club_id: int, db: AsyncSession = Depends(get_db)):
    """Удалить клуб"""
    res = await db.execute(select(models.Club).filter(models.Club.id == club_id))
    club = res.scalars().first()
    if not club:
        raise HTTPException(status_code=404, detail="Клуб не найден")
    await db.delete(club)
    await db.commit()
    return MessageResponse(success=True, message="Клуб удален")
