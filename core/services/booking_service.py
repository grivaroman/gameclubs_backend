"""Бизнес-логика бронирования и освобождения ПК."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models
from core.finance import debit_user_balance
from core.fraud import evaluate_admin_pc_override, evaluate_booking_success, evaluate_failed_payment
from core.services.access import user_can_manage_club
from core.services.exceptions import (
    AuthRequiredError,
    ConflictError,
    ForbiddenError,
    InsufficientFundsError,
    NotFoundError,
    ValidationError,
)
from core.ws import safe_send_pc_command


@dataclass
class BookingResult:
    booking_id: int
    pc_number: int
    duration_minutes: int
    message: str


@dataclass
class FreeSeatResult:
    pc_number: int
    message: str


class BookingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _lock_active_user(self, user_id: int) -> models.User:
        res = await self.db.execute(
            select(models.User)
            .filter(models.User.id == user_id, models.User.is_active == 1)
            .with_for_update()
        )
        user = res.scalars().first()
        if not user:
            raise AuthRequiredError("Необходима авторизация")
        return user

    async def book_seat(self, *, user_id: int, pc_id: int, package_id: int) -> BookingResult:
        user = await self._lock_active_user(user_id)

        res = await self.db.execute(
            select(models.Computer).filter(models.Computer.id == pc_id).with_for_update()
        )
        pc = res.scalars().first()
        if not pc:
            raise NotFoundError("Компьютер не найден")
        if pc.status != "free":
            raise ConflictError("Место уже занято")

        res_club = await self.db.execute(
            select(models.Club).filter(models.Club.id == pc.club_id, models.Club.status == "active")
        )
        if not res_club.scalars().first():
            raise ConflictError("Клуб сейчас недоступен для бронирования")

        res_pkg = await self.db.execute(
            select(models.Package).filter(
                models.Package.id == package_id,
                models.Package.club_id == pc.club_id,
            )
        )
        package = res_pkg.scalars().first()
        if not package:
            raise NotFoundError("Тариф не найден")
        if package.pc_category != pc.category:
            raise ValidationError("Тариф не подходит для выбранного ПК")
        if package.price < 0 or package.duration_minutes < 1:
            raise ValidationError("Тариф настроен некорректно")

        if user.balance < package.price:
            await evaluate_failed_payment(
                self.db,
                user=user,
                event_type="player_booking_insufficient_funds",
                amount=package.price,
                balance=user.balance,
                club_id=pc.club_id,
            )
            await self.db.commit()
            raise InsufficientFundsError(f"Недостаточно средств. Нужно {package.price}₸")

        pc.status = "busy"
        pc.current_user_id = user.id
        pc.end_time = datetime.utcnow() + timedelta(minutes=package.duration_minutes)
        booking = models.Booking(
            user_id=user.id,
            computer_id=pc.id,
            amount_paid=package.price,
            status="active",
            starts_at=datetime.utcnow(),
            ends_at=pc.end_time,
        )
        self.db.add(booking)
        await self.db.flush()
        await debit_user_balance(
            self.db,
            user=user,
            amount=package.price,
            kind="booking_debit",
            club_id=pc.club_id,
            booking_id=booking.id,
            reason="Бронирование ПК",
            metadata={"pc_id": pc.id, "package_id": package.id, "duration_minutes": package.duration_minutes},
        )
        self.db.add(models.Notification(
            kind="booking",
            club_id=pc.club_id,
            title="Новое бронирование",
            message=f"ПК #{pc.number} забронирован на {package.duration_minutes} мин.",
        ))
        await evaluate_booking_success(self.db, user=user, pc=pc, package=package)
        await self.db.commit()

        await safe_send_pc_command(pc.id, {"command": "unlock", "user": user.email})
        return BookingResult(
            booking_id=booking.id,
            pc_number=pc.number,
            duration_minutes=package.duration_minutes,
            message=f"Бронирование на {package.duration_minutes} мин. успешно!",
        )

    async def free_seat(self, *, actor: models.User, pc_id: int) -> FreeSeatResult:
        res = await self.db.execute(select(models.Computer).filter(models.Computer.id == pc_id))
        pc = res.scalars().first()
        if not pc:
            raise NotFoundError("Компьютер не найден")

        can_manage = await user_can_manage_club(self.db, actor, pc.club_id)
        if not can_manage and pc.current_user_id != actor.id:
            raise ForbiddenError("Вы не можете освободить чужое место")

        if can_manage:
            await evaluate_admin_pc_override(self.db, admin=actor, pc=pc, new_status="free")

        pc.status = "free"
        pc.current_user_id = None
        pc.end_time = None
        await self.db.execute(
            update(models.Booking)
            .filter(models.Booking.computer_id == pc.id, models.Booking.status == "active")
            .values(status="completed")
        )
        await self.db.commit()

        await safe_send_pc_command(pc.id, {"command": "lock"})
        return FreeSeatResult(pc_number=pc.number, message="Место успешно освобождено!")
