"""Локальный демо-сидинг для просмотра /admin.

Запускать ПОСЛЕ применения миграций и при поднятой БД:
    python3 seed_local.py

Создаёт (идемпотентно):
  - владельца клуба:  owner@local.test / owner-local-12345  (role=admin)
  - клиента:          client@local.test / client-local-12345 (role=user)
  - активный клуб с несколькими ПК и парой позиций меню
  - одну заявку на бронь (status=pending) и одну активную бронь — для вкладки «Заявки»
"""
import asyncio
from datetime import datetime, timedelta

import local_bcrypt_fix  # noqa: F401  — должен импортироваться до passlib
from passlib.context import CryptContext
from sqlalchemy.future import select

import models

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def get_or_create_user(db, email, password, role):
    res = await db.execute(select(models.User).filter(models.User.email == email))
    user = res.scalars().first()
    if user:
        return user
    user = models.User(
        email=email,
        hashed_password=pwd_context.hash(password),
        role=role,
        is_active=1,
        balance=100000,
    )
    db.add(user)
    await db.flush()
    return user


async def main():
    async with models.SessionLocal() as db:
        owner = await get_or_create_user(db, "owner@local.test", "owner-local-12345", "admin")
        client = await get_or_create_user(db, "client@local.test", "client-local-12345", "user")

        res = await db.execute(select(models.Club).filter(models.Club.name == "Demo Club Almaty"))
        club = res.scalars().first()
        if not club:
            club = models.Club(
                name="Demo Club Almaty",
                address="ул. Абая, 10",
                city="Алматы",
                working_hours="10:00–02:00",
                contact_phone="+7 700 000 00 00",
                description="Демо-клуб для локального просмотра админки.",
                amenities="VIP, PS5, напитки, снеки",
                owner_id=owner.id,
                status="active",
                approved_at=datetime.utcnow(),
            )
            db.add(club)
            await db.flush()

        res = await db.execute(select(models.Computer).filter(models.Computer.club_id == club.id))
        computers = res.scalars().all()
        if not computers:
            computers = []
            for i in range(1, 9):
                category = "VIP" if i > 6 else "Standard"
                pc = models.Computer(number=i, category=category, club_id=club.id, status="free")
                db.add(pc)
                computers.append(pc)
            await db.flush()

        res = await db.execute(select(models.Product).filter(models.Product.club_id == club.id))
        if not res.scalars().first():
            db.add(models.Product(name="Кола 0.5", price=500, club_id=club.id))
            db.add(models.Product(name="Бургер", price=1800, club_id=club.id))

        res = await db.execute(
            select(models.Booking).filter(models.Booking.computer_id == computers[0].id, models.Booking.status == "pending")
        )
        if not res.scalars().first():
            db.add(models.Booking(
                user_id=client.id,
                computer_id=computers[0].id,
                status="pending",
                starts_at=datetime.utcnow() + timedelta(hours=1),
                ends_at=datetime.utcnow() + timedelta(hours=3),
            ))
        # одна активная бронь, чтобы заполнить колонку «Текущие брони»
        active_pc = computers[3]
        res = await db.execute(
            select(models.Booking).filter(models.Booking.computer_id == active_pc.id, models.Booking.status == "active")
        )
        if not res.scalars().first():
            active_pc.status = "busy"
            active_pc.current_user_id = client.id
            active_pc.end_time = datetime.utcnow() + timedelta(hours=1)
            db.add(models.Booking(
                user_id=client.id,
                computer_id=active_pc.id,
                status="active",
                starts_at=datetime.utcnow(),
                ends_at=active_pc.end_time,
            ))

        await db.commit()

    print("Сидинг готов.")
    print("  Владелец (вход в /admin): owner@local.test / owner-local-12345")
    print("  Клиент:                   client@local.test / client-local-12345")
    print("  Суперадмин (/superadmin): admin@local.test / admin-local-12345")


if __name__ == "__main__":
    asyncio.run(main())
