from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from schemas import ClubResponse, ClubCreate, ClubListResponse, GameResponse, PackageResponse, ComputerResponse, ProductResponse
import models
from core.dependencies import get_db

router = APIRouter(prefix="/clubs", tags=["clubs"])

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
        booking_mode=club.booking_mode or "request",
        booking_deposit=club.booking_deposit or 0,
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
            description=c.description,
            booking_mode=c.booking_mode or "request",
            booking_deposit=c.booking_deposit or 0,
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

@router.get("/{club_id}/computers", response_model=list[ComputerResponse])
async def get_club_computers(club_id: int, db: AsyncSession = Depends(get_db)):
    """Список компьютеров клуба с их статусами"""
    res = await db.execute(
        select(models.Club.id).filter(models.Club.id == club_id, models.Club.status == "active")
    )
    if not res.scalars().first():
        raise HTTPException(status_code=404, detail="Клуб не найден")
    res_pc = await db.execute(
        select(models.Computer)
        .filter(models.Computer.club_id == club_id)
        .order_by(models.Computer.number)
    )
    return res_pc.scalars().all()


@router.get("/{club_id}/products", response_model=list[ProductResponse])
async def get_club_products(club_id: int, db: AsyncSession = Depends(get_db)):
    """Список товаров клуба"""
    res = await db.execute(
        select(models.Club.id).filter(models.Club.id == club_id, models.Club.status == "active")
    )
    if not res.scalars().first():
        raise HTTPException(status_code=404, detail="Клуб не найден")
    res_prod = await db.execute(
        select(models.Product).filter(models.Product.club_id == club_id).order_by(models.Product.name)
    )
    return res_prod.scalars().all()


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
