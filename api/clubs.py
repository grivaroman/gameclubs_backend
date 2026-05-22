from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from schemas import ClubResponse, ClubCreate, ClubListResponse, GameResponse, PackageResponse
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
        city=club.city,
        photo_url=club.photo_url,
        contact_phone=club.contact_phone,
        working_hours=club.working_hours,
        description=club.description,
        amenities=club.amenities,
        games=[GameResponse(id=g.id, name=g.name) for g in club.games],
        packages=[
            PackageResponse(
                id=p.id,
                name=p.name,
                price=p.price,
                duration_minutes=p.duration_minutes,
                paid_minutes=p.paid_minutes,
                bonus_minutes=p.bonus_minutes or 0,
                pc_category=p.pc_category,
            )
            for p in club.packages
        ]
    )

@router.get("", response_model=list[ClubListResponse])
async def get_clubs(db: AsyncSession = Depends(get_db)):
    """Получить список всех клубов (краткая информация)"""
    res = await db.execute(
        select(models.Club)
        .options(selectinload(models.Club.games), selectinload(models.Club.packages))
        .filter(models.Club.status == "active")
    )
    clubs = res.scalars().all()
    return [
        ClubListResponse(
            id=c.id,
            name=c.name,
            address=c.address,
            city=c.city,
            photo_url=c.photo_url,
            working_hours=c.working_hours,
            description=c.description
        ) for c in clubs
    ]

@router.get("/{club_id}", response_model=ClubResponse)
async def get_club(club_id: int, db: AsyncSession = Depends(get_db)):
    """Получить полную информацию о клубе по ID"""
    res = await db.execute(
        select(models.Club)
        .options(selectinload(models.Club.games), selectinload(models.Club.packages))
        .filter(models.Club.id == club_id, models.Club.status == "active")
    )
    club = res.scalars().first()
    if not club:
        raise HTTPException(status_code=404, detail="Клуб не найден")
    return club_to_response(club)

@router.post("", response_model=ClubResponse)
async def create_club(data: ClubCreate, db: AsyncSession = Depends(get_db)):
    """Создать новый клуб"""
    raise HTTPException(status_code=403, detail="Создание клуба доступно через заявку владельца")

@router.put("/{club_id}", response_model=ClubResponse)
async def update_club(club_id: int, data: ClubCreate, db: AsyncSession = Depends(get_db)):
    """Обновить информацию о клубе"""
    raise HTTPException(status_code=403, detail="Обновление клуба доступно владельцу через CRM")

@router.delete("/{club_id}")
async def delete_club(club_id: int, db: AsyncSession = Depends(get_db)):
    """Удалить клуб"""
    raise HTTPException(status_code=403, detail="Удаление клуба доступно только суперадмину")
